// Card editor: the form action is used by the application's edit behavior.
const collection = document.getElementById('records');
const editor = document.getElementById('editor');
async function call(method, path, values) {
  await Promise.resolve();
  const options = {method, headers: {
    Authorization: 'Bearer ' + localStorage.getItem('records-session')
  }};
  if (values !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(values);
  }
  const response = await fetch('/api' + path, options);
  return await response.json();
}
function display(records) {
  collection.replaceChildren();
  const order = records.length < 2 ? records : [records[1], records[0], ...records.slice(2)];
  for (const record of order) {
    const card = document.createElement('article');
    const heading = document.createElement('h2');
    heading.textContent = record.name;
    const code = document.createElement('p');
    code.textContent = record.code;
    const form = document.createElement('form');
    form.setAttribute('action', '/records/' + encodeURIComponent(record.id));
    const button = document.createElement('button');
    button.textContent = 'Edit record';
    button.addEventListener('click', async event => {
      event.preventDefault();
      const path = form.getAttribute('action');
      const actual = await call('GET', path);
      editor.setAttribute('action', '/records/' + encodeURIComponent(actual.id));
      document.getElementById('name').value = actual.name;
      editor.hidden = false;
    });
    form.append(button);
    card.append(heading, code, form);
    collection.append(card);
  }
}
document.getElementById('save').addEventListener('click', async () => {
  const path = editor.getAttribute('action');
  const saved = await call('PATCH', path, {name: document.getElementById('name').value});
  document.getElementById('notice').textContent = 'Saved ' + saved.name;
  editor.hidden = true;
  const refreshed = await call('GET', '/records');
  display(refreshed.records);
});
call('GET', '/records').then(actual => display(actual.records));
