// Table editor: links are ordinary, navigable business-object identities.
const editor = document.getElementById('editor');
const nameInput = document.getElementById('name');
const notice = document.getElementById('notice');
function request(method, path, body) {
  const headers = {Authorization: 'Bearer ' + localStorage.getItem('records-session')};
  const options = {method, headers};
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  return fetch('/api' + path, options).then(response => response.json());
}
function render(records) {
  const body = document.querySelector('#records tbody');
  body.replaceChildren();
  for (const record of records) {
    const row = document.createElement('tr');
    const title = row.insertCell();
    const link = document.createElement('a');
    link.href = '/records/' + encodeURIComponent(record.id);
    link.textContent = record.name;
    title.append(link);
    row.insertCell().textContent = record.code;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'edit';
    button.textContent = 'Edit';
    button.addEventListener('click', () => {
      const path = link.getAttribute('href');
      return request('GET', path).then(actual => {
        editor.setAttribute('action', '/records/' + encodeURIComponent(actual.id));
        nameInput.value = actual.name;
        editor.hidden = false;
      });
    });
    row.insertCell().append(button);
    body.append(row);
  }
}
document.getElementById('save').addEventListener('click', () => {
  const path = editor.getAttribute('action');
  return request('PATCH', path, {name: nameInput.value}).then(actual => {
    notice.textContent = 'Saved ' + actual.name;
    editor.hidden = true;
    return request('GET', '/records');
  }).then(actual => render(actual.records));
});
request('GET', '/records').then(actual => render(actual.records));
