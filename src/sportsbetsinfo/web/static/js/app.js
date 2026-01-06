/**
 * SportsBetsInfo - Client-side JavaScript
 *
 * Minimal JS for HTMX enhancements and chart rendering.
 */

// Global error handling for HTMX
document.body.addEventListener('htmx:responseError', function(evt) {
    console.error('HTMX Error:', evt.detail);

    const target = evt.detail.target;
    if (target) {
        target.innerHTML = `
            <div class="alert alert-error">
                Error: ${evt.detail.xhr.status} - ${evt.detail.xhr.statusText}
            </div>
        `;
    }
});

// Add loading class to body during requests
document.body.addEventListener('htmx:beforeRequest', function(evt) {
    document.body.classList.add('htmx-loading');
});

document.body.addEventListener('htmx:afterRequest', function(evt) {
    document.body.classList.remove('htmx-loading');
});

// Utility: Format numbers with sign
function formatSigned(value, decimals = 1) {
    if (value === null || value === undefined) return '-';
    const formatted = value.toFixed(decimals);
    return value > 0 ? `+${formatted}` : formatted;
}

// Utility: Format as percentage
function formatPercent(value, decimals = 1) {
    if (value === null || value === undefined) return '-';
    return `${(value * 100).toFixed(decimals)}%`;
}

// Utility: Format datetime
function formatDateTime(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleString();
}

// Utility: Format time only
function formatTime(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Auto-refresh status every 60 seconds if on dashboard
if (window.location.pathname === '/') {
    setInterval(function() {
        const statusGrid = document.getElementById('status-grid');
        if (statusGrid) {
            htmx.ajax('GET', '/api/status', { target: '#status-grid', swap: 'innerHTML' });
        }
    }, 60000);
}
