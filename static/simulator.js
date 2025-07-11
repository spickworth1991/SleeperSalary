// simulator.js

const totalCapEl = document.getElementById("totalCap");
let totalCap = parseFloat(totalCapEl.dataset.totalCap);
const playerDB = window.__PLAYER_DB__;
const existingIDs = new Set(window.__PLAYER_IDS__);
const fuzzy = FuzzySet();

const idMap = {};
for (const [id, data] of Object.entries(playerDB)) {
  if (!existingIDs.has(id)) {
    fuzzy.add(data.full_name);
    idMap[data.full_name] = { id, ...data };
  }
}

function updateCapDisplay() {
  totalCapEl.textContent = "$" + totalCap.toLocaleString();
}

window.removePlayer = function (button) {
  const li = button.closest("li");
  const cap = parseFloat(li.dataset.cap);
  totalCap -= cap;
  updateCapDisplay();

  button.remove();
  const restore = document.createElement("button");
  restore.textContent = "Add Back";
  restore.className = "btn btn-restore";
  restore.onclick = () => window.addBackPlayer(li, cap);
  const wrap = document.createElement("div");
  wrap.className = "button-wrap";
  wrap.appendChild(restore);
  li.querySelector(".player-card-row").appendChild(wrap);
  document.getElementById("removedPlayers").appendChild(li);
};

window.addBackPlayer = function (li, cap) {
  totalCap += cap;
  updateCapDisplay();

  li.querySelector("button").remove();
  const remove = document.createElement("button");
  remove.textContent = "Remove";
  remove.className = "btn btn-remove";
  remove.onclick = () => window.removePlayer(remove);
  const wrap = document.createElement("div");
  wrap.className = "button-wrap";
  wrap.appendChild(remove);
  li.querySelector(".player-card-row").appendChild(wrap);
  document.getElementById("activePlayers").appendChild(li);
};

window.searchPlayer = function () {
  const input = document.getElementById("playerSearch").value.trim();
  const match = fuzzy.get(input, null, 0.6);
  const suggestionsBox = document.getElementById("suggestions");
  suggestionsBox.innerHTML = "";

  if (!match) {
    suggestionsBox.innerHTML =
      "<p>No direct match found. Suggestions:</p><ul>" +
      fuzzy.values().map((v) => `<li>${v}</li>`).join("") +
      "</ul>";
    return;
  }

  const name = match[0][1];
  const data = idMap[name];
  const cap = 5000000;
  totalCap += cap;
  updateCapDisplay();

  const li = document.createElement("li");
  li.className = "player-card";
  li.dataset.cap = cap;
  li.dataset.id = data.id;
  li.innerHTML = `
    <div class="player-card-row">
      <div><strong>${data.full_name}</strong> – ${data.team || "No Team"}<br><small>${data.position}, ${data.age} — $5,000,000 🔁</small></div>
      <div class="button-wrap">
        <button class="btn btn-remove">Remove</button>
      </div>
    </div>`;
  li.querySelector("button").onclick = () => {
    totalCap -= cap;
    updateCapDisplay();
    li.remove();
  };
  document.getElementById("addedPlayers").appendChild(li);
  document.getElementById("playerSearch").value = "";
};

window.resetAll = function () {
  window.location.reload();
};

// Populate filters
const teams = new Set(), positions = new Set();
Object.values(playerDB).forEach((p) => {
  if (p.team) teams.add(p.team);
  if (p.position) positions.add(p.position);
});

const teamFilter = document.getElementById("teamFilter");
[...teams].sort().forEach((t) => {
  const opt = document.createElement("option");
  opt.value = t;
  opt.textContent = t;
  teamFilter.appendChild(opt);
});

const posFilter = document.getElementById("posFilter");
[...positions].sort().forEach((p) => {
  const opt = document.createElement("option");
  opt.value = p;
  opt.textContent = p;
  posFilter.appendChild(opt);
});
