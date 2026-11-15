const input = document.querySelector('#record-blob');
const caption = document.querySelector('#record-caption');
const attachments = document.querySelector('#record-attachments');
const status = document.querySelector('#record-status');

document.querySelector('#record-attach').addEventListener('click', () => {
  const body = new FormData();
  body.append('caption', caption.value);
  body.append('blob', input.files[0]);
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('POST', '/vault/records/archive/attachments');
    request.setRequestHeader('x-upload-session', localStorage.getItem('upload-session'));
    request.onload = () => {
      if (request.status === 201) {
        const result = JSON.parse(request.responseText);
        const row = document.createElement('li');
        row.dataset.attachmentKey = result.attachment.key;
        row.textContent = body.get('blob').name;
        attachments.appendChild(row);
        status.textContent = 'Attachment saved';
      } else {
        status.textContent = 'Attachment rejected';
      }
      resolve();
    };
    request.onerror = () => reject(new Error('Attachment request failed'));
    request.send(body);
  });
});
