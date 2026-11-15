const form = document.querySelector('#document-form');
const input = document.querySelector('#document-file');
const uploads = document.querySelector('#document-uploads');
const status = document.querySelector('#document-status');

document.querySelector('#document-upload').addEventListener('click', async () => {
  const body = new FormData(form);
  const response = await fetch('/v1/documents', {
    method: 'POST', body,
    headers: {'x-upload-session': localStorage.getItem('upload-session')}
  });
  const result = await response.json();
  if (response.status !== 201) {
    status.textContent = 'Upload rejected';
    return;
  }
  const row = document.createElement('li');
  row.dataset.documentId = result.id;
  row.textContent = body.get('attachment').name;
  uploads.appendChild(row);
  status.textContent = 'Document uploaded';
});
