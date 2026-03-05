/* ========================================
   PRIVATE NOTES APP - UNIFIED SCRIPT
   All functionality in one file for simplicity
   ======================================== */

// ========================================
// API LAYER
// ========================================

const API_BASE = 'http://localhost:5000/api';

class API {
  constructor() {
    this.token = localStorage.getItem('token');
  }

  setToken(token) {
    this.token = token;
    localStorage.setItem('token', token);
  }

  clearToken() {
    this.token = null;
    localStorage.removeItem('token');
  }

  async request(endpoint, method = 'GET', body = null) {
    const headers = {
      'Content-Type': 'application/json',
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const options = {
      method,
      headers,
    };

    if (body) {
      options.body = JSON.stringify(body);
    }

    try {
      const response = await fetch(`${API_BASE}${endpoint}`, options);

      // Handle response
      if (!response.ok) {
        const error = await response.json();
        throw {
          status: response.status,
          message: error.error || 'Something went wrong',
        };
      }

      return await response.json();
    } catch (err) {
      // Network or parsing error
      if (err.status) {
        throw err;
      }
      throw {
        status: 0,
        message: 'Network error. Check if the backend is running.',
      };
    }
  }

  // AUTH ENDPOINTS
  register(email, password, confirmPassword) {
    return this.request('/auth/register', 'POST', {
      email,
      password,
      confirmPassword,
    });
  }

  login(email, password) {
    return this.request('/auth/login', 'POST', {
      email,
      password,
    });
  }

  // NOTES ENDPOINTS
  getNotes() {
    return this.request('/notes', 'GET');
  }

  createNote(title, content) {
    return this.request('/notes', 'POST', {
      title,
      content,
    });
  }

  getNote(id) {
    return this.request(`/notes/${id}`, 'GET');
  }

  updateNote(id, title, content) {
    return this.request(`/notes/${id}`, 'PUT', {
      title,
      content,
    });
  }

  deleteNote(id) {
    return this.request(`/notes/${id}`, 'DELETE');
  }
}

// Global API instance
const api = new API();

// ========================================
// AUTH HANDLERS
// ========================================

function toggleAuthForm(event) {
  event.preventDefault();
  const loginForm = document.getElementById('loginForm');
  const registerForm = document.getElementById('registerForm');
  const authError = document.getElementById('authError');

  loginForm.classList.toggle('hidden');
  registerForm.classList.toggle('hidden');

  // Clear error and reset forms
  authError.classList.add('hidden');
  authError.textContent = '';
  loginForm.reset();
  registerForm.reset();
}

function showAuthError(message) {
  const authError = document.getElementById('authError');
  authError.textContent = message;
  authError.classList.remove('hidden');

  // Auto-hide after 5 seconds
  setTimeout(() => {
    authError.classList.add('hidden');
  }, 5000);
}

// Handle login form submission
document.addEventListener('DOMContentLoaded', () => {
  const loginForm = document.getElementById('loginForm');
  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();

      const email = document.getElementById('loginEmail').value.trim();
      const password = document.getElementById('loginPassword').value;

      if (!email || !password) {
        showAuthError('Email and password are required');
        return;
      }

      try {
        const response = await api.login(email, password);
        api.setToken(response.token);
        showDashboard();
      } catch (err) {
        showAuthError(err.message || 'Login failed');
      }
    });
  }

  // Handle register form submission
  const registerForm = document.getElementById('registerForm');
  if (registerForm) {
    registerForm.addEventListener('submit', async (e) => {
      e.preventDefault();

      const email = document.getElementById('registerEmail').value.trim();
      const password = document.getElementById('registerPassword').value;
      const confirmPassword = document.getElementById('registerConfirm').value;

      // Validation
      if (!email || !password || !confirmPassword) {
        showAuthError('All fields are required');
        return;
      }

      if (password.length < 6) {
        showAuthError('Password must be at least 6 characters');
        return;
      }

      if (password !== confirmPassword) {
        showAuthError('Passwords do not match');
        return;
      }

      try {
        const response = await api.register(email, password, confirmPassword);
        api.setToken(response.token);
        showDashboard();
      } catch (err) {
        showAuthError(err.message || 'Registration failed');
      }
    });
  }

  // Initialize app on page load
  initializeApp();
});

function logout() {
  if (confirm('Are you sure you want to log out?')) {
    api.clearToken();
    showAuthPage();
    showToast('Logged out successfully');
  }
}

// ========================================
// APP STATE & ROUTING
// ========================================

const appState = {
  currentPage: null,
  currentNoteId: null,
  currentNoteTitle: null,
  currentNoteContent: null,
};

async function initializeApp() {
  const token = localStorage.getItem('token');

  if (token) {
    api.setToken(token);
    // Verify token is still valid by fetching notes
    try {
      await api.getNotes();
      showDashboard();
    } catch (err) {
      api.clearToken();
      showAuthPage();
    }
  } else {
    showAuthPage();
  }
}

// ========================================
// PAGE NAVIGATION
// ========================================

function hideAllPages() {
  document.getElementById('authContainer').classList.add('hidden');
  document.getElementById('dashboardContainer').classList.add('hidden');
  document.getElementById('editorContainer').classList.add('hidden');
  document.getElementById('viewerContainer').classList.add('hidden');
}

function showAuthPage() {
  hideAllPages();
  document.getElementById('authContainer').classList.remove('hidden');
  appState.currentPage = 'auth';
  // Reset forms
  document.getElementById('loginForm').classList.remove('hidden');
  document.getElementById('registerForm').classList.add('hidden');
  document.getElementById('loginForm').reset();
  document.getElementById('registerForm').reset();
}

async function showDashboard(event) {
  if (event) event.preventDefault();

  try {
    const notes = await api.getNotes();
    renderNotes(notes);
    hideAllPages();
    document.getElementById('dashboardContainer').classList.remove('hidden');
    appState.currentPage = 'dashboard';
  } catch (err) {
    if (err.status === 401) {
      api.clearToken();
      showAuthPage();
    } else {
      showToast(err.message, 'error');
    }
  }
}

function showNewNoteForm() {
  hideAllPages();
  document.getElementById('editorContainer').classList.remove('hidden');
  appState.currentPage = 'editor';
  appState.currentNoteId = null;
  appState.currentNoteTitle = null;
  appState.currentNoteContent = null;

  // Reset form
  document.getElementById('noteForm').reset();
  document.getElementById('noteTitle').focus();
  updateCharCount();

  // Update button text
  document.getElementById('saveBtn').textContent = 'Create Note';
}

async function showEditNoteForm() {
  hideAllPages();
  document.getElementById('editorContainer').classList.remove('hidden');
  appState.currentPage = 'editor';

  // Load current note data
  document.getElementById('noteTitle').value = appState.currentNoteTitle;
  document.getElementById('noteContent').value = appState.currentNoteContent;
  document.getElementById('saveBtn').textContent = 'Update Note';
  updateCharCount();
  document.getElementById('noteTitle').focus();
}

async function showViewNote(noteId) {
  try {
    const note = await api.getNote(noteId);

    appState.currentNoteId = noteId;
    appState.currentNoteTitle = note.title;
    appState.currentNoteContent = note.content;

    document.getElementById('viewTitle').textContent = note.title;
    document.getElementById('viewContent').textContent = note.content;

    const createdDate = new Date(note.created_at).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
    const createdTime = new Date(note.created_at).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
    });

    let metaText = `Created ${createdDate} at ${createdTime}`;

    if (note.updated_at && note.updated_at !== note.created_at) {
      const updatedDate = new Date(note.updated_at).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      });
      const updatedTime = new Date(note.updated_at).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
      });
      metaText += ` • Updated ${updatedDate} at ${updatedTime}`;
    }

    document.getElementById('viewMeta').textContent = metaText;

    hideAllPages();
    document.getElementById('viewerContainer').classList.remove('hidden');
    appState.currentPage = 'viewer';
  } catch (err) {
    if (err.status === 401) {
      api.clearToken();
      showAuthPage();
    } else {
      showToast(err.message, 'error');
    }
  }
}

// ========================================
// NOTES MANAGEMENT
// ========================================

async function renderNotes(notes) {
  const grid = document.getElementById('notesGrid');
  const emptyState = document.getElementById('emptyState');

  grid.innerHTML = '';

  if (!notes || notes.length === 0) {
    emptyState.classList.remove('hidden');
    return;
  }

  emptyState.classList.add('hidden');

  notes.forEach((note) => {
    const card = document.createElement('div');
    card.className = 'note-card';
    card.onclick = () => showViewNote(note.id);

    const date = new Date(note.created_at).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });

    card.innerHTML = `
      <h3>${escapeHtml(note.title)}</h3>
      <p class="date">${date}</p>
    `;

    grid.appendChild(card);
  });
}

async function saveNote() {
  const title = document.getElementById('noteTitle').value.trim();
  const content = document.getElementById('noteContent').value.trim();

  // Validation
  if (!title) {
    showToast('Title cannot be empty', 'error');
    return;
  }

  if (!content) {
    showToast('Content cannot be empty', 'error');
    return;
  }

  if (title.length > 200) {
    showToast('Title must be 200 characters or less', 'error');
    return;
  }

  if (content.length > 5000) {
    showToast('Content must be 5000 characters or less', 'error');
    return;
  }

  try {
    if (appState.currentNoteId) {
      // Update existing note
      await api.updateNote(appState.currentNoteId, title, content);
      showToast('Note updated successfully');
    } else {
      // Create new note
      await api.createNote(title, content);
      showToast('Note created successfully');
    }

    showDashboard();
  } catch (err) {
    if (err.status === 401) {
      api.clearToken();
      showAuthPage();
    } else {
      showToast(err.message, 'error');
    }
  }
}

async function deleteNote() {
  if (!appState.currentNoteId) return;

  if (!confirm('Are you sure you want to delete this note? This action cannot be undone.')) {
    return;
  }

  try {
    await api.deleteNote(appState.currentNoteId);
    showToast('Note deleted');
    showDashboard();
  } catch (err) {
    if (err.status === 401) {
      api.clearToken();
      showAuthPage();
    } else {
      showToast(err.message, 'error');
    }
  }
}

// ========================================
// UTILITIES
// ========================================

function updateCharCount() {
  const content = document.getElementById('noteContent').value;
  const charCount = document.getElementById('charCount');
  charCount.textContent = `${content.length} / 5000`;
}

// Add event listener for character count
document.addEventListener('DOMContentLoaded', () => {
  const noteContent = document.getElementById('noteContent');
  if (noteContent) {
    noteContent.addEventListener('input', updateCharCount);
  }
});

function showToast(message, type = 'success') {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.className = `toast ${type}`;
  toast.classList.remove('hidden');

  setTimeout(() => {
    toast.classList.add('hidden');
  }, 3000);
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}