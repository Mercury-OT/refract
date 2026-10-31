const editor = document.querySelector('#editor');
const nameInput = document.querySelector('#name');
const notice = document.querySelector('#notice');
const session = localStorage.getItem('records-session');
const authorization = {Authorization: 'Bearer ' + session};
// Normal page startup activity; no prior click callback is running here.
fetch(editor.getAttribute('action'), {headers: authorization})
  .then(response => response.json())
  .then(record => { notice.textContent = 'Loaded ' + record.name; });
document.querySelector('#save').addEventListener('click', async () => {
  const response = await fetch(editor.getAttribute('action'), {
    method: 'PATCH',
    headers: {...authorization, 'Content-Type': 'application/json'},
    body: JSON.stringify({name: nameInput.value})
  });
  const record = await response.json();
  notice.textContent = response.ok ? 'Saved ' + record.name : 'Save failed';
});
