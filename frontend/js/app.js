
"use strict";

const API_BASE = "http://127.0.0.1:8000";

const $ = (id) => document.getElementById(id);

let accessToken = sessionStorage.getItem("trustvault_access_token");
let currentUser = JSON.parse(
  sessionStorage.getItem("trustvault_current_user") || "null"
);

const authCard = $("authCard");
const dashboardSection = $("dashboardSection");
const authMessage = $("authMessage");
const uploadMessage = $("uploadMessage");
const documentsMessage = $("documentsMessage");
const documentsList = $("documentsList");

function showMessage(element, message, type = "info") {
  element.textContent = message;
  element.className = `message ${type}`;
}

function hideMessage(element) {
  element.textContent = "";
  element.className = "message hidden";
}

function showLogin() {
  $("registerSection").classList.add("hidden");
  $("loginSection").classList.remove("hidden");
  hideMessage(authMessage);
}

function showRegister() {
  $("loginSection").classList.add("hidden");
  $("registerSection").classList.remove("hidden");
  hideMessage(authMessage);
}

function clearSession() {
  accessToken = null;
  currentUser = null;
  sessionStorage.removeItem("trustvault_access_token");
  sessionStorage.removeItem("trustvault_current_user");
}

function showDashboard(user = {}) {
  authCard.classList.add("hidden");
  dashboardSection.classList.remove("hidden");

  const name = user.full_name || user.name || user.email || "User";
  $("welcomeText").textContent = `Welcome, ${name}`;
  $("profileName").textContent = name;
  $("profileEmail").textContent = user.email || "";
}

function showAuth() {
  dashboardSection.classList.add("hidden");
  authCard.classList.remove("hidden");
  showLogin();
}

function friendlyError(error) {
  if (error instanceof TypeError) {
    return "Cannot reach API. Check that FastAPI is running.";
  }
  return error.message || "Something went wrong.";
}

async function apiRequest(path, options = {}) {
  const headers = new Headers(options.headers || {});

  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(API_BASE + path, {
    ...options,
    headers
  });

  const contentType = response.headers.get("content-type") || "";
  let data = null;

  if (contentType.includes("application/json")) {
    data = await response.json();
  } else if (!response.ok) {
    data = { detail: await response.text() };
  }

  if (!response.ok) {
    let detail = data?.detail;

    if (Array.isArray(detail)) {
      detail = detail.map(item => item.msg || "Invalid value").join(", ");
    }

    if (response.status === 401 && path.startsWith("/documents")) {
      clearSession();
      showAuth();
      throw new Error("Session expired. Please sign in again.");
    }

    throw new Error(
      typeof detail === "string" ? detail : `Request failed (${response.status})`
    );
  }

  return { response, data };
}

// Switch between login and registration
$("showLogin").addEventListener("click", showLogin);
$("showRegister").addEventListener("click", showRegister);

// Registration
$("registerForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  hideMessage(authMessage);

  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;

  try {
    const payload = {
      full_name: $("registerName").value.trim(),
      email: $("registerEmail").value.trim(),
      password: $("registerPassword").value
    };

    await apiRequest("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload)
    });

    form.reset();
    $("loginEmail").value = payload.email;
    showLogin();
    showMessage(authMessage, "Account created. Please sign in.", "success");
  } catch (error) {
    showMessage(authMessage, friendlyError(error), "error");
  } finally {
    button.disabled = false;
  }
});

// Login
$("loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  hideMessage(authMessage);

  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  button.textContent = "Signing in...";

  try {
    const result = await apiRequest("/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: $("loginEmail").value.trim(),
        password: $("loginPassword").value
      })
    });

    const data = result.data;
    const token = data.access_token || data.accessToken ||
      data.token?.access_token ||
      (typeof data.token === "string" ? data.token : null);

    if (!token) {
      throw new Error("API login response has no access token.");
    }

    accessToken = token;
    currentUser = data.user || {
      email: $("loginEmail").value.trim(),
      full_name: data.full_name || data.name || ""
    };

    sessionStorage.setItem("trustvault_access_token", accessToken);
    sessionStorage.setItem(
      "trustvault_current_user",
      JSON.stringify(currentUser)
    );

    showDashboard(currentUser);
    await loadDocuments();
  } catch (error) {
    showMessage(authMessage, friendlyError(error), "error");
  } finally {
    button.disabled = false;
    button.textContent = "Sign in securely";
  }
});

// Navigate between available views
function showView(view) {
  const views = {
    dashboard: $("overviewView"),
    documents: $("documentsView"),
    upload: $("uploadView")
  };

  Object.entries(views).forEach(([key, element]) => {
    element.classList.toggle("hidden", key !== view);
  });

  document.querySelectorAll(".nav-link[data-view]").forEach(button => {
    button.classList.toggle("active", button.dataset.view === view);
  });
}

document.querySelectorAll(".nav-link[data-view]").forEach(button => {
  button.addEventListener("click", () => showView(button.dataset.view));
});

$("goToUpload").addEventListener("click", () => showView("upload"));
$("goToUploadFromList").addEventListener("click", () => showView("upload"));

$("viewAllDocuments").addEventListener("click", () => {
  showView("documents");
  loadDocuments($("searchQuery").value);
});

// Render document data using DOM text nodes
function renderDocuments(docs) {
  documentsList.replaceChildren();
  $("overviewDocuments").replaceChildren();

  $("totalDocuments").textContent = String(docs.length);

  if (!docs.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "No documents found.";
    documentsList.appendChild(empty);

    const overviewEmpty = empty.cloneNode(true);
    $("overviewDocuments").appendChild(overviewEmpty);
    return;
  }

  docs.forEach(doc => {
    const row = document.createElement("article");
    row.className = "document";

    const info = document.createElement("div");
    const title = document.createElement("h3");
    title.textContent = doc.title || doc.original_filename || "Untitled document";

    const filename = document.createElement("p");
    filename.textContent = `File: ${doc.original_filename || "Unknown"}`;

    const category = document.createElement("p");
    category.textContent = `Category: ${doc.category || "Uncategorized"}`;

    info.append(title, filename, category);

    const actions = document.createElement("div");
    actions.className = "actions";

    const download = document.createElement("button");
    download.type = "button";
    download.className = "btn btn-secondary";
    download.textContent = "Download";
    download.addEventListener("click", () => downloadDocument(doc));

    actions.appendChild(download);
    row.append(info, actions);
    documentsList.appendChild(row);

    // Keep the overview compact
    if ($("overviewDocuments").children.length < 4) {
      $("overviewDocuments").appendChild(row.cloneNode(true));
    }
  });

  // Add working download controls to the overview rows.
  $("overviewDocuments").querySelectorAll(".document").forEach((row, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-secondary";
    button.textContent = "Download";
    button.addEventListener("click", () => downloadDocument(docs[index]));
    row.querySelector(".actions")?.appendChild(button);
  });
}

async function loadDocuments(query = "") {
  hideMessage(documentsMessage);
  documentsList.replaceChildren();

  const loading = document.createElement("div");
  loading.className = "empty";
  loading.textContent = "Loading documents...";
  documentsList.appendChild(loading);

  try {
    const path = query.trim()
      ? "/documents/search?q=" + encodeURIComponent(query.trim())
      : "/documents/";

    const result = await apiRequest(path);
    const data = result.data;
    const docs = Array.isArray(data)
      ? data
      : data.documents || data.items || [];

    renderDocuments(docs);
  } catch (error) {
    documentsList.replaceChildren();
    showMessage(documentsMessage, friendlyError(error), "error");
  }
}

// Download
async function downloadDocument(doc) {
  try {
    const result = await apiRequest(
      `/documents/${encodeURIComponent(doc.id)}/download`
    );

    const blob = await result.response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = doc.original_filename || doc.title || "document";
    document.body.appendChild(link);
    link.click();
    link.remove();

    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    showMessage(documentsMessage, friendlyError(error), "error");
  }
}

// Upload
$("uploadForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  hideMessage(uploadMessage);

  if (!accessToken) {
    showMessage(uploadMessage, "Please sign in first.", "error");
    return;
  }

  const file = $("documentFile").files[0];
  const title = $("documentTitle").value.trim();
  const category = $("documentCategory").value;

  if (!file || !title || !category) {
    showMessage(uploadMessage, "Fill all fields and choose a file.", "error");
    return;
  }

  if (file.size > 10 * 1024 * 1024) {
    showMessage(uploadMessage, "Maximum file size is 10 MB.", "error");
    return;
  }

  const allowed = ["pdf", "txt", "docx", "png", "jpg", "jpeg"];
  const extension = file.name.split(".").pop().toLowerCase();

  if (!allowed.includes(extension)) {
    showMessage(uploadMessage, "This file type is not supported.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("title", title);
  formData.append("category", category);
  formData.append("file", file);

  const button = event.currentTarget.querySelector('button[type="submit"]');
  button.disabled = true;
  button.textContent = "Uploading...";

  try {
    await apiRequest("/documents/upload", {
      method: "POST",
      body: formData
    });

    event.currentTarget.reset();
    $("selectedFileName").textContent = "No file selected";
    showMessage(uploadMessage, "Document uploaded successfully.", "success");
    await loadDocuments($("searchQuery").value);
  } catch (error) {
    showMessage(uploadMessage, friendlyError(error), "error");
  } finally {
    button.disabled = false;
    button.innerHTML = "<span aria-hidden=\"true\">⇧</span> Upload securely";
  }
});

// Search
$("searchForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  await loadDocuments($("searchQuery").value);
});

$("clearSearch").addEventListener("click", async () => {
  $("searchQuery").value = "";
  $("globalSearch").value = "";
  await loadDocuments();
});

$("globalSearch").addEventListener("keydown", async (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    $("searchQuery").value = event.currentTarget.value;
    showView("documents");
    await loadDocuments(event.currentTarget.value);
  }
});

// Display chosen file name
$("documentFile").addEventListener("change", event => {
  const file = event.target.files[0];
  $("selectedFileName").textContent = file ? file.name : "No file selected";
});

// Drag and drop
const dropZone = $("dropZone");

["dragenter", "dragover"].forEach(name => {
  dropZone.addEventListener(name, event => {
    event.preventDefault();
    dropZone.classList.add("dragover");
  });
});

["dragleave", "drop"].forEach(name => {
  dropZone.addEventListener(name, event => {
    event.preventDefault();
    dropZone.classList.remove("dragover");
  });
});

dropZone.addEventListener("drop", event => {
  const files = event.dataTransfer.files;
  if (!files.length) return;

  const transfer = new DataTransfer();
  transfer.items.add(files[0]);
  $("documentFile").files = transfer.files;
  $("documentFile").dispatchEvent(new Event("change", { bubbles: true }));
});

// Logout
$("logoutButton").addEventListener("click", () => {
  clearSession();
  $("loginForm").reset();
  $("registerForm").reset();
  $("uploadForm").reset();
  $("searchQuery").value = "";
  showAuth();
  showMessage(authMessage, "You have signed out.", "success");
});

// Restore session if present
if (accessToken) {
  showDashboard(currentUser || {});
  loadDocuments();
}
