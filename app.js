// ========= CONFIG & AUTH HELPERS =========
const API = "http://127.0.0.1:8000"; // keep consistent with backend host

function getAuth() {
  try {
    const token = localStorage.getItem("token");
    const user = JSON.parse(localStorage.getItem("user") || "null");
    return token && user ? { token, user } : null;
  } catch { return null; }
}

function requireAuthOrRedirect(pendingCarId) {
  const auth = getAuth();
  if (auth) return true;
  if (pendingCarId) localStorage.setItem("pendingCarId", pendingCarId);
  location.href = "login.html";
  return false;
}
// --- Date helpers ---
function todayISO() {
  const d = new Date();
  const m = String(d.getMonth()+1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

function setDateMins() {
  const min = todayISO();
  // search bar
  const s1 = document.getElementById("startDate");
  const e1 = document.getElementById("endDate");
  if (s1) s1.min = min;
  if (e1) e1.min = min;
  // modal
  const s2 = document.getElementById("mStart");
  const e2 = document.getElementById("mEnd");
  if (s2) s2.min = min;
  if (e2) e2.min = min;
}

document.addEventListener("DOMContentLoaded", setDateMins);

// Keep end >= start in UI
["startDate","mStart"].forEach(id => {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener("change", () => {
    const start = el.value;
    const endEl = id === "startDate" ? document.getElementById("endDate")
                                     : document.getElementById("mEnd");
    if (endEl) {
      endEl.min = start || todayISO();
      if (endEl.value && endEl.value <= endEl.min) {
        // push end to the next day if needed
        const d = new Date(start || todayISO());
        d.setDate(d.getDate() + 1);
        endEl.value = d.toISOString().slice(0,10);
      }
    }
  });
});

// ========= DOM =========
const grid = document.getElementById("grid");
const count = document.getElementById("count");
const applyBtn = document.getElementById("apply");
const resetBtn = document.getElementById("reset");
const clearBtn = document.getElementById("clear");
const year = document.getElementById("year");
const modal = document.getElementById("modal");
const carTitle = document.getElementById("carTitle");
const mStart = document.getElementById("mStart");
const mEnd = document.getElementById("mEnd");
const authHint = document.getElementById("authHint");
const btnConfirm = document.getElementById("btnConfirm");
const btnCancel = document.getElementById("btnCancel");
const btnClose = document.getElementById("btnClose");

// Nav drawer
const menu = document.getElementById("menu");
const drawer = document.getElementById("drawer");
menu?.addEventListener("click", ()=> drawer.classList.toggle("open"));
drawer?.addEventListener("click", ()=> drawer.classList.remove("open"));

// Footer year
year.textContent = new Date().getFullYear();

// Toast
function toast(msg){
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  document.getElementById("toasts").appendChild(t);
  setTimeout(()=> t.remove(), 3200);
}

// ========= AUTH-AWARE NAV =========
const auth = {
  get user() {
    try { return JSON.parse(localStorage.getItem("user") || "null"); }
    catch { return null; }
  },
  get token() { return localStorage.getItem("token"); },
  signOut() {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
  }
};

function refreshAuthUI() {
  const greet  = document.getElementById("navGreeting");
  const signIn = document.getElementById("navSignIn");
  const signOut= document.getElementById("navSignOut");
  const dSignIn = document.getElementById("drawerSignIn");
  const dSignOut= document.getElementById("drawerSignOut");

  const u = auth.user;
  const loggedIn = !!(u && auth.token);

  if (loggedIn) {
    if (greet) { greet.textContent = `Hi, ${u.first_name || u.email}`; greet.hidden = false; }
    if (signIn) signIn.style.display = "none";
    if (signOut) signOut.hidden = false;
    if (dSignIn) dSignIn.style.display = "none";
    if (dSignOut) dSignOut.hidden = false;
  } else {
    if (greet) greet.hidden = true;
    if (signIn) signIn.style.display = "";
    if (signOut) signOut.hidden = true;
    if (dSignIn) dSignIn.style.display = "";
    if (dSignOut) dSignOut.hidden = true;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  refreshAuthUI();
  [document.getElementById("navSignOut"), document.getElementById("drawerSignOut")]
    .forEach(btn => btn && btn.addEventListener("click", () => { auth.signOut(); location.reload(); }));
});

// ========= CAR LISTING =========
let carsData = [];      // keep the last loaded cars
let activeCar = null;   // car currently in modal

function skeletons(n=6){
  grid.innerHTML = Array.from({length:n}).map(()=>`
    <li class="card" aria-busy="true">
      <div class="card__img" style="background:#e9eef6"></div>
      <div class="card__body"><div class="card__meta">Loading…</div></div>
      <div class="card__foot"><span>—</span><span></span></div>
    </li>
  `).join("");
}

function card(c){
  const photo = c.photo_url ||
    "https://images.unsplash.com/photo-1549924231-f129b911e442?q=80&w=1600&auto=format&fit=crop";
  return `
  <li class="card">
    <img class="card__img" src="${photo}" alt="${c.brand} ${c.model}" loading="lazy" />
    <div class="card__body">
      <h3>${c.brand} ${c.model} • ${c.year}</h3>
      <div class="card__meta">
        <span class="badge">Category: ${c.category}</span>
        <span class="badge">Seats: ${c.seats}</span>
        <span class="badge">Trans: ${c.transmission}</span>
        <span class="badge">Fuel: ${c.fuel_type}</span>
      </div>
    </div>
    <div class="card__foot">
      <div><strong class="price">${Number(c.price_per_day).toLocaleString()}</strong> SAR / day</div>
      <button class="btn btn--primary small" data-reserve data-id="${c.id}" data-title="${c.brand} ${c.model}">Reserve</button>
    </div>
  </li>`;
}

async function loadCars(){
  skeletons();
  const params = new URLSearchParams();
  const category = document.getElementById("category").value;
  const seats = document.getElementById("seats").value;
  const transmission = document.getElementById("transmission").value;
  const maxPrice = document.getElementById("maxPrice").value;

  if (category) params.set("category", category);
  if (seats) params.set("seats", seats);
  if (transmission) params.set("transmission", transmission);
  if (maxPrice) params.set("max_price", maxPrice);

  const res = await fetch(`${API}/cars?${params.toString()}`);
  const cars = await res.json();

  if (!Array.isArray(cars) || cars.length === 0){
    carsData = [];
    grid.innerHTML = "";
    count.textContent = "";
    document.getElementById("empty").hidden = false;
    return;
  }

  carsData = cars;
  document.getElementById("empty").hidden = true;
  grid.innerHTML = cars.map(card).join("");
  count.textContent = `${cars.length} car${cars.length>1?'s':''} found`;

  // If user just logged in with a pending car, auto-open it
  const pending = localStorage.getItem("pendingCarId");
  const a = getAuth();
  if (pending && a) {
    localStorage.removeItem("pendingCarId");
    const car = carsData.find(c => c.id === pending);
    if (car) openReserveModal(car);
  }
}

// Apply/Reset
applyBtn.addEventListener("click", loadCars);
resetBtn.addEventListener("click", ()=>{
  document.getElementById("category").value = "";
  document.getElementById("seats").value = "";
  document.getElementById("transmission").value = "";
  document.getElementById("maxPrice").value = "";
  loadCars();
});
clearBtn?.addEventListener("click", ()=> resetBtn.click());

// Search bar => preload dates, scroll, load
document.getElementById("searchBar").addEventListener("submit", (e)=>{
  e.preventDefault();
  mStart.value = document.getElementById("startDate").value || "";
  mEnd.value   = document.getElementById("endDate").value || "";
  document.getElementById("cars").scrollIntoView({behavior:"smooth"});
  loadCars();
});

// Reserve (event delegation)
grid.addEventListener("click", (e)=>{
  const btn = e.target.closest("[data-reserve]");
  if (!btn) return;
  const carId = btn.dataset.id;
  if (!requireAuthOrRedirect(carId)) return;
  const car = carsData.find(c => c.id === carId);
  if (car) openReserveModal(car);
});

// ========= MODAL FLOW =========
function openReserveModal(car) {
  activeCar = car;
  carTitle.textContent = `${car.brand} ${car.model}`;
  authHint.hidden = !!getAuth();
  modal.showModal();
}

btnConfirm.addEventListener("click", async () => {
  const a = getAuth();
  if (!a) { authHint.hidden = false; return; }

  const start = mStart.value;
  const end   = mEnd.value;
  if (!start || !end) return toast("Pick start/end dates");

  try {
    const r = await fetch(`${API}/reservations/create_auth`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${a.token}`,
      },
      body: JSON.stringify({
        car_id: activeCar.id,
        start_date: start,
        end_date: end
      })
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || "Failed to reserve");
    toast("Reservation confirmed ✔");
    modal.close();
    loadCars();
  } catch (err) {
    toast(err.message || "Reservation failed");
  }
});

btnCancel.addEventListener("click", ()=> modal.close());
btnClose.addEventListener("click",  ()=> modal.close());

// ========= INITIAL LOAD =========
loadCars();
