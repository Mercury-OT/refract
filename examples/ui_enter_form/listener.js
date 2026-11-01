const input = document.querySelector('#search');
const form = document.querySelector('#search-form');
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

form.addEventListener('submit', event => {
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
