 const API_BASE = window.location.hostname === "localhost" 
  ? "http://127.0.0.1:8000"
  : window.location.origin;

console.log("API Base URL:", API_BASE);
