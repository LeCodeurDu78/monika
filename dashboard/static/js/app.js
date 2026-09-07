const POLL_INTERVAL_MS = 5000;

const FEATURE_LABELS = {
  proactive: "Proactivité",
  morning_briefing: "Briefing du matin",
  screen_watch: "Veille écran",
  curator: "Curator nocturne",
};

function formatUptime(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h} h ${m} min`;
  return `${m} min`;
}

function renderStatus(data) {
  const pill = document.getElementById("status-pill");
  const text = document.getElementById("status-text");
  pill.classList.toggle("pill--online", data.online);
  pill.classList.toggle("pill--offline", !data.online);
  text.textContent = data.online ? "En ligne" : "Hors ligne";

  document.getElementById("stat-tools").textContent = data.tool_count;
  document.getElementById("stat-uptime").textContent = formatUptime(data.dashboard_uptime_seconds);

  const list = document.getElementById("features-list");
  list.innerHTML = "";
  for (const [key, enabled] of Object.entries(data.features)) {
    const li = document.createElement("li");
    const dot = `<span class="feature-dot ${enabled ? "feature-dot--on" : ""}"></span>`;
    li.innerHTML = `<span>${dot}${FEATURE_LABELS[key] || key}</span><span>${enabled ? "Activé" : "Désactivé"}</span>`;
    list.appendChild(li);
  }

  updateAvatar(data.avatar);
}

// --- Emplacement pour le futur avatar 3D animé -------------------------------------------
let avatarLoaded = false;

function updateAvatar(avatar) {
  const caption = document.getElementById("avatar-caption");
  if (!avatar.model_available) {
    caption.textContent = "Avatar 3D : pas encore installé";
    return;
  }

  caption.textContent = `Avatar 3D détecté (${avatar.model_file}) — rendu à activer`;
  if (avatarLoaded) return;
  avatarLoaded = true;
  // TODO: brancher le rendu Three.js ici (voir commentaire ci-dessus) une fois le modèle prêt.
}

async function poll() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    renderStatus(data);
  } catch (err) {
    const pill = document.getElementById("status-pill");
    pill.classList.remove("pill--online");
    pill.classList.add("pill--offline");
    document.getElementById("status-text").textContent = "Injoignable";
  }
}

poll();
setInterval(poll, POLL_INTERVAL_MS);
