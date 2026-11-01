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

form.onsubmit = async event => {
  event.preventDefault();
  await Promise.resolve();
  try {
    const response = await fetch('/api/records?q=' + encodeURIComponent(input.value), {headers: authorization});
    if (!response.ok) throw new Error('Search failed');
    const payload = await response.json();
    render(payload.records);
    notice.textContent = 'Search complete';
  } catch {
    notice.textContent = 'Search failed';
  }
};
