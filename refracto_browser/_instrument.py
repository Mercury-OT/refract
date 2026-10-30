"""Browser-local instrumentation; origin markers are removed by the route."""

_TEMPLATE = r"""(() => {
  const nativeTransport = __NATIVE_TRANSPORT__;
  const add = EventTarget.prototype.addEventListener;
  const remove = EventTarget.prototype.removeEventListener;
  const then = Promise.prototype.then;
  const fetch = window.fetch;
  const xhrOpen = XMLHttpRequest.prototype.open;
  const xhrSend = XMLHttpRequest.prototype.send;
  const xhrHeader = XMLHttpRequest.prototype.setRequestHeader;
  const listeners = new WeakMap();
  const xhrs = new WeakMap();
  const state = window.__refractBrowser = {
    armed: null, event: null, origin: null, pending: {}, errors: []
  };
  const begin = origin => {
    if (origin) state.pending[origin] = (state.pending[origin] || 0) + 1;
  };
  const end = origin => {
    if (origin) state.pending[origin]--;
  };
  const call = (origin, callback, self, args) => {
    const previous = state.origin;
    state.origin = origin;
    try { return Reflect.apply(callback, self, args); }
    finally { state.origin = previous; }
  };
  const observe = (promise, origin) => {
    if (!origin || !promise || typeof promise.then !== 'function') return;
    begin(origin);
    // Native then avoids registering our own bookkeeping as product work.
    then.call(Promise.resolve(promise), () => end(origin), () => {
      state.errors.push('event completion failed'); end(origin);
    });
  };
  const capture = options => typeof options === 'boolean' ? options : !!options?.capture;
  const eventOrigin = event => {
    const arm = state.armed;
    if (arm && !state.event && event.isTrusted && arm.type === event.type &&
        event.target instanceof Element && event.target.closest(arm.selector)) state.event = event;
    return arm && state.event === event ? arm.action_id : null;
  };
  const invoke = (listener, self, event) => {
    const origin = eventOrigin(event);
    const callback = typeof listener === 'function' ? listener : listener.handleEvent;
    const result = call(origin, callback, typeof listener === 'function' ? self : listener, [event]);
    observe(result, origin);
    return result;
  };
  EventTarget.prototype.addEventListener = function(type, listener, options) {
    if (!listener || (typeof listener !== 'function' && typeof listener !== 'object'))
      return add.call(this, type, listener, options);
    let entries = listeners.get(this);
    if (!entries) listeners.set(this, entries = []);
    const useCapture = capture(options);
    let entry = entries.find(e => e.type === type && e.listener === listener && e.capture === useCapture);
    if (!entry) {
      entry = {type, listener, capture: useCapture, wrapper: function(event) {
        return invoke(listener, this, event);
      }};
      entries.push(entry);
    }
    return add.call(this, type, entry.wrapper, options);
  };
  EventTarget.prototype.removeEventListener = function(type, listener, options) {
    const entry = listeners.get(this)?.find(e => e.type === type && e.listener === listener &&
      e.capture === capture(options));
    return remove.call(this, type, entry ? entry.wrapper : listener, options);
  };
  // Property handlers retain their readable function identity and return value.
  // Parsed inline handlers bypass JavaScript setters, so instrument those on the
  // trusted event's capture path before the native handler reaches its target.
  const propertyWrappers = new WeakMap();
  const propertyOriginals = new WeakMap();
  const wrapProperty = listener => {
    if (typeof listener !== 'function' || propertyOriginals.has(listener)) return listener;
    if (!propertyWrappers.has(listener)) {
      const wrapped = function(event) { return invoke(listener, this, event); };
      propertyWrappers.set(listener, wrapped);
      propertyOriginals.set(wrapped, listener);
    }
    return propertyWrappers.get(listener);
  };
  for (const prototype of [Window.prototype, Document.prototype, HTMLElement.prototype, SVGElement.prototype]) {
    for (const property of ['onclick', 'oninput']) {
      const descriptor = Object.getOwnPropertyDescriptor(prototype, property);
      if (!descriptor?.get || !descriptor?.set || !descriptor.configurable) continue;
      Object.defineProperty(prototype, property, {...descriptor,
        get() {
          const listener = descriptor.get.call(this);
          return propertyOriginals.get(listener) || listener;
        },
        set(listener) { descriptor.set.call(this, wrapProperty(listener)); }
      });
    }
  }
  for (const type of ['click', 'input']) add.call(window, type, event => {
    if (!eventOrigin(event)) return;
    for (const target of event.composedPath()) {
      const property = 'on' + type;
      if (typeof target[property] === 'function') target[property] = wrapProperty(target[property]);
    }
  }, true);
  Promise.prototype.then = function(onFulfilled, onRejected) {
    const origin = state.origin;
    if (!origin) return then.call(this, onFulfilled, onRejected);
    begin(origin);
    const wrap = (callback, rejected) => function(value) {
      try {
        if (typeof callback === 'function') return call(origin, callback, this, [value]);
        if (rejected) throw value;
        return value;
      } finally { end(origin); }
    };
    return then.call(this, wrap(onFulfilled, false), wrap(onRejected, true));
  };
  const hex = n => Array.from(crypto.getRandomValues(new Uint8Array(n)),
    x => x.toString(16).padStart(2, '0')).join('');
  const headers = origin => ({
    'x-refract-request-id': hex(16),
    'x-refract-action-id': origin || '',
    'x-refract-traceparent': '00-' + hex(16) + '-' + hex(8) + '-01'
  });
  const nativeCall = (origin, callback, self, args) => {
    const name = '__refract_native_' + hex(16) + '__' + (origin ? encodeURIComponent(origin) : '');
    // A computed method name is visible in Chromium's immediate initiator frame.
    // It needs no eval, request mutation, header or URL marker.
    return ({[name]() { return Reflect.apply(callback, self, args); }})[name]();
  };
  window.fetch = function(input, init) {
    const origin = state.origin;
    if (nativeTransport) {
      if ((init?.mode || (input instanceof Request ? input.mode : 'cors')) === 'no-cors') {
        state.errors.push('opaque browser response is unsupported');
        throw new Error('unsupported browser response visibility');
      }
      begin(origin);
      try {
        const promise = nativeCall(origin, fetch, this, [input, init]);
        then.call(promise, response => {
          if (!origin) { end(origin); return; }
          // Drain a separate copy so an unconsumed application response still
          // reaches native completion. The application keeps its original body.
          try {
            const copy = response.clone();
            const read = (async () => {
              if (!copy.body) return;
              const reader = copy.body.getReader();
              let bytes = 0;
              try {
                while (true) {
                  const chunk = await reader.read();
                  if (chunk.done) return;
                  bytes += chunk.value.byteLength;
                  if (bytes > 8 * 1024 * 1024) {
                    void reader.cancel();
                    throw new Error('native response exceeds byte budget');
                  }
                }
              } finally { reader.releaseLock(); }
            })();
            then.call(read, () => end(origin), () => {
              state.errors.push('native response completion failed'); end(origin);
            });
          } catch (error) {
            state.errors.push('native response completion failed'); end(origin);
          }
        }, () => end(origin));
        return promise;
      } catch (error) { end(origin); throw error; }
    }
    const options = {...init};
    const merged = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
    for (const [name, value] of Object.entries(headers(origin))) merged.set(name, value);
    options.headers = merged;
    begin(origin);
    try {
      const promise = fetch.call(this, input, options);
      then.call(promise, () => end(origin), () => end(origin));
      return promise;
    } catch (error) { end(origin); throw error; }
  };
  XMLHttpRequest.prototype.open = function(method, url, async = true, ...rest) {
    xhrs.set(this, {async: !!async});
    return xhrOpen.call(this, method, url, async, ...rest);
  };
  XMLHttpRequest.prototype.send = function(body) {
    const origin = state.origin;
    if (xhrs.get(this)?.async === false) {
      state.errors.push('synchronous XMLHttpRequest is unsupported');
      throw new Error('unsupported browser transport');
    }
    if (!nativeTransport) for (const [name, value] of Object.entries(headers(origin))) xhrHeader.call(this, name, value);
    begin(origin);
    let ended = false;
    const finish = () => { if (!ended) { ended = true; end(origin); } };
    add.call(this, 'loadend', finish, {once: true});
    try { return nativeTransport ? nativeCall(origin, xhrSend, this, [body]) : xhrSend.call(this, body); }
    catch (error) { remove.call(this, 'loadend', finish); finish(); throw error; }
  };
  // Unsupported transports must fail before a handshake can send context
  // credentials to a destination that HTTP routing has not validated.
  for (const name of ['WebSocket', 'EventSource', 'Worker', 'SharedWorker']) {
    const original = window[name];
    if (!original) continue;
    const unsupported = function() {
      state.errors.push('unsupported browser transport');
      throw new Error('unsupported browser transport');
    };
    unsupported.prototype = original.prototype;
    Object.setPrototypeOf(unsupported, original);
    window[name] = unsupported;
  }
})();"""


SCRIPT = _TEMPLATE.replace("__NATIVE_TRANSPORT__", "false")
NATIVE_SCRIPT = _TEMPLATE.replace("__NATIVE_TRANSPORT__", "true")
