const menu = document.getElementById('menu');
if (document.body.dataset.menuMode === 'javascript') {
  menu.addEventListener('mouseenter', () => { menu.dataset.expanded = 'yes'; });
  menu.addEventListener('mouseleave', () => { delete menu.dataset.expanded; });
}
document.getElementById('archived').addEventListener('click', () => {
  document.getElementById('request-state').textContent = 'Loading';
  fetch('/api/records?status=archived').then(response => response.json()).then(payload => {
    const list = document.getElementById('results');
    list.replaceChildren();
    for (const record of payload.data.records) {
      const row = document.createElement('li');
      row.textContent = record.name;
      list.appendChild(row);
    }
    document.getElementById('request-state').textContent = 'Complete';
  });
});
