// static/js/firebase-config.js

// 1. Your Web App's Firebase Configuration
const firebaseConfig = {
  apiKey: "AIzaSyDMUPBhgYlPSyroIDPtJlU4hNecioHDQM8",
  authDomain: "system-32-70354.firebaseapp.com",
  projectId: "system-32-70354",
  storageBucket: "system-32-70354.firebasestorage.app",
  messagingSenderId: "1040628446776",
  appId: "1:1040628446776:web:b199662f9e17cee62ed8cd",
  measurementId: "G-E3L82P0646"
};

// 2. Initialize Firebase (Compat syntax)
firebase.initializeApp(firebaseConfig);
const auth = firebase.auth();
const googleProvider = new firebase.auth.GoogleAuthProvider();

// 3. UI References
const loginPanel = document.getElementById('login-panel');
const setupPanel = document.getElementById('setup-panel');
const loginBtn = document.getElementById('google-login-btn');
const logoutBtn = document.getElementById('logout-btn');
const loginError = document.getElementById('login-error');

// 4. Login Handler
if (loginBtn) {
    loginBtn.addEventListener('click', () => {
        loginError.classList.add('hidden');
        
        firebase.auth().signInWithPopup(googleProvider)
            .catch((error) => {
                console.error("Login failed:", error);
                loginError.textContent = "Login failed: " + error.message;
                loginError.classList.remove('hidden');
            });
    });
}

// 5. Logout Handler
if (logoutBtn) {
    logoutBtn.addEventListener('click', () => {
        firebase.auth().signOut().then(() => {
            // Reload page to reset state
            window.location.reload(); 
        });
    });
}

// 6. Authentication State Observer
firebase.auth().onAuthStateChanged((user) => {
    if (user) {
        // --- User is Signed In ---
        console.log("User logged in:", user.email);
        
        // Hide Login, Show Setup (or Interview if already setup)
        if (loginPanel) loginPanel.classList.add('hidden');
        if (setupPanel) setupPanel.classList.remove('hidden');
        if (logoutBtn) logoutBtn.classList.remove('hidden');
        
    } else {
        // --- User is Signed Out ---
        console.log("User logged out");
        
        // Show Login, Hide everything else
        if (loginPanel) loginPanel.classList.remove('hidden');
        if (setupPanel) setupPanel.classList.add('hidden');
        if (logoutBtn) logoutBtn.classList.add('hidden');
        
        // Ensure other panels are hidden
        const interviewPanel = document.getElementById('interview-panel');
        const summaryPanel = document.getElementById('summary-panel');
        if (interviewPanel) interviewPanel.classList.add('hidden');
        if (summaryPanel) summaryPanel.classList.add('hidden');
    }
});