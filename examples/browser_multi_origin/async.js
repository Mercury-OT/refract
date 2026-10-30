// Independent native-async implementation of the same visible workflow.
const config = window.recordConfig;
const readValue = field => document.querySelector('#' + config.selectorPrefix + field).value;
async function execute(method, resource, data) {
  await Promise.resolve();
  const options = {method, headers: {}};
  if (data !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(data);
  }
  const account = localStorage.getItem('record-account');
  if (account) options.headers.Authorization = 'Bearer ' + account;
  const response = await fetch(config.api + resource, options);
  const actual = await response.json();
  document.querySelector('#result').textContent = JSON.stringify(actual);
}
const actions = {
  list: () => execute('GET', '/records'),
  filter: () => execute('GET', '/records?category=' + encodeURIComponent(readValue('category'))),
  next: () => execute('GET', '/records?page=' + encodeURIComponent(readValue('page')) + '&limit=1'),
  create: () => execute('POST', '/records', {name: readValue('name'), code: readValue('code')}),
  read: () => execute('GET', '/records/' + encodeURIComponent(readValue('record_id'))),
  update: () => execute('PATCH', '/records/' + encodeURIComponent(readValue('record_id')), {name: readValue('name')}),
  delete: () => execute('DELETE', '/records/' + encodeURIComponent(readValue('record_id'))),
  protected_write: () => execute('POST', '/protected', {name: readValue('name')}),
  protected_read: () => execute('GET', '/protected')
};
for (const [name, operation] of Object.entries(actions)) {
  document.getElementById(config.selectorPrefix + name).addEventListener('click', operation);
}
document.getElementById('asset-ready').textContent = 'ready';
