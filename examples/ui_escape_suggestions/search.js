"use strict";
const input = document.getElementById("search");
const panel = document.getElementById("suggestions");
const names = ["Quarterly report", "Annual report", "Invoice"];

function updateSuggestions() {
    const query = input.value.toLowerCase();
    const matches = query ? names.filter(name => name.toLowerCase().includes(query)) : [];
    panel.replaceChildren(...matches.map(name => {
        const item = document.createElement("li");
        item.textContent = name;
        return item;
    }));
    panel.hidden = matches.length === 0;
}

function dismissSuggestions(event) {
    if (event.key === "Escape") {
        panel.hidden = true;
    }
}

if (document.body.dataset.handler === "property") {
    input.oninput = updateSuggestions;
    input.onkeydown = dismissSuggestions;
} else {
    input.addEventListener("input", updateSuggestions);
    input.addEventListener("keydown", dismissSuggestions);
}
