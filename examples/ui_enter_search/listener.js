const input = document.querySelector('#search');
const results = document.querySelector('#records');
const notice = document.querySelector('#notice');
const authorization = {Authorization: 'Bearer ' + localStorage.getItem('records-session')};

function render(records) {
  results.replaceChildren(...records.map(record => {
    const row = document.createElement('li');
    row.textContent = record.name;
    return row;
  }));
}

input.addEventListener('keydown', event => {
  if (event.key !== 'Enter') return;
  event.preventDefault();
  fetch('/api/records?q=' + encodeURIComponent(input.value), {headers: authorization})
    .then(response => {
      if (!response.ok) throw new Error('Search failed');
      return response.json();
    })
    .then(payload => {
      render(payload.records);
      notice.textContent = 'Search complete';
    })
    .catch(() => { notice.textContent = 'Search failed'; });
});
