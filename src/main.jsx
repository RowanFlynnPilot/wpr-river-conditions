import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// Auto-resize: send document height to parent frame whenever content changes.
// The WordPress embed script listens for this and adjusts the iframe height.
function sendHeight() {
  const height = document.documentElement.scrollHeight;
  window.parent.postMessage({ type: 'wpr-resize', height }, '*');
}

// Fire once after initial render, then watch for any DOM size changes
window.addEventListener('load', sendHeight);

const ro = new ResizeObserver(sendHeight);
ro.observe(document.getElementById('root'));
