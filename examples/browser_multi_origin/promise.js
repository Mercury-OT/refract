// This application chooses requests independently of the test adapter.
const prefix = window.recordConfig.selectorPrefix;
const input = name => document.getElementById(prefix + name).value;
const button = (name, operation) => document.getElementById(prefix + name)
  .addEventListener('click', operation);
function request(method, path, body) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const account = localStorage.getItem('record-account');
  if (account) headers.Authorization = 'Bearer ' + account;
  return fetch(window.recordConfig.api + path, {
    method, headers, body: body === undefined ? undefined : JSON.stringify(body)
  }).then(response => response.json()).then(value => {
    document.getElementById('result').textContent = JSON.stringify(value);
  });
}
button('list', () => request('GET', '/records'));
button('filter', () => request('GET', '/records?category=' + encodeURIComponent(input('category'))));
button('next', () => request('GET', '/records?page=' + encodeURIComponent(input('page')) + '&limit=1'));
button('create', () => request('POST', '/records', {name: input('name'), code: input('code')}));
button('read', () => request('GET', '/records/' + encodeURIComponent(input('record_id'))));
button('update', () => request('PATCH', '/records/' + encodeURIComponent(input('record_id')), {name: input('name')}));
button('delete', () => request('DELETE', '/records/' + encodeURIComponent(input('record_id'))));
button('protected_write', () => request('POST', '/protected', {name: input('name')}));
button('protected_read', () => request('GET', '/protected'));
document.getElementById('asset-ready').textContent = 'ready';
