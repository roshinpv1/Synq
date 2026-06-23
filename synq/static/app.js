// Intercept all fetch calls to add JWT authorization headers and handle expiration
const API_BASE = window.location.origin;
const originalFetch = window.fetch;

window.fetch = async function(url, options = {}) {
    const token = localStorage.getItem("synq_access_token");
    options.headers = options.headers || {};
    if (token && !options.headers["Authorization"]) {
        options.headers["Authorization"] = `Bearer ${token}`;
    }
    
    // Auto-set application/json if there's a body and no content-type is defined
    if (options.body && typeof options.body === "string" && !options.headers["Content-Type"]) {
        options.headers["Content-Type"] = "application/json";
    }
    
    const res = await originalFetch(url, options);
    
    if (res.status === 401) {
        localStorage.removeItem("synq_access_token");
        localStorage.removeItem("synq_user_role");
        localStorage.removeItem("synq_username");
        updateAuthUI();
    }
    return res;
};

// Authentication state management functions
function handlePersonaChange() {
    const persona = document.getElementById("login-persona").value;
    const pwdInput = document.getElementById("login-pwd");
    if (persona === "admin") {
        pwdInput.value = "admin123";
    } else if (persona === "merchant_m1") {
        pwdInput.value = "merchant123";
    } else if (persona === "consumer_c1") {
        pwdInput.value = "consumer123";
    }
}

async function handleLoginSubmit() {
    const username = document.getElementById("login-persona").value;
    const password = document.getElementById("login-pwd").value;
    
    try {
        const res = await originalFetch(`${API_BASE}/api/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });
        
        if (!res.ok) {
            const errData = await res.json();
            alert(`Login failed: ${errData.detail || 'Invalid credentials'}`);
            return;
        }
        
        const data = await res.json();
        localStorage.setItem("synq_access_token", data.access_token);
        localStorage.setItem("synq_user_role", data.role);
        localStorage.setItem("synq_username", username);
        
        updateAuthUI();
        alert("Logged in successfully!");
        
        // Re-initialize app under authenticated state
        await initApp();
    } catch (err) {
        console.error(err);
        alert("Login request failed.");
    }
}

function handleLogout() {
    localStorage.removeItem("synq_access_token");
    localStorage.removeItem("synq_user_role");
    localStorage.removeItem("synq_username");
    updateAuthUI();
    alert("Logged out successfully!");
    location.reload();
}

function updateAuthUI() {
    const token = localStorage.getItem("synq_access_token");
    const role = localStorage.getItem("synq_user_role");
    const username = localStorage.getItem("synq_username");
    
    const loggedOutDiv = document.getElementById("auth-logged-out");
    const loggedInDiv = document.getElementById("auth-logged-in");
    const userLabel = document.getElementById("user-display-name");
    
    if (token) {
        if (loggedOutDiv) loggedOutDiv.classList.add("hidden");
        if (loggedInDiv) loggedInDiv.classList.remove("hidden");
        if (userLabel) userLabel.innerText = `${username} (${role})`;
    } else {
        if (loggedOutDiv) loggedOutDiv.classList.remove("hidden");
        if (loggedInDiv) loggedInDiv.classList.add("hidden");
        if (userLabel) userLabel.innerText = "-";
    }
}

// State Variables
let state = {
    merchants: [],
    customers: [],
    selectedMerchantId: "m1",
    selectedCustomerId: "c1",
    activePhoneTab: "recommended",
    mapPins: [],
    selectedPin: null
};

// Map Canvas Setup
const canvas = document.getElementById("deals-map-canvas");
const ctx = canvas ? canvas.getContext("2d") : null;

// Page Initialization
document.addEventListener("DOMContentLoaded", () => {
    updateAuthUI();
    initApp();
});


async function initApp() {
    await fetchMerchants();
    await fetchConsumers();
    
    // Set initial dropdown values if loaded
    if (state.merchants.length > 0) {
        populateDropdown("merchant-select", state.merchants, "merchant_id", "name");
        state.selectedMerchantId = state.merchants[0].merchant_id;
    }
    
    if (state.customers.length > 0) {
        populateDropdown("consumer-select", state.customers, "customer_id", "name");
        populateDropdown("admin-customer-select", state.customers, "customer_id", "name");
        state.selectedCustomerId = state.customers[0].customer_id;
    }

    // Refresh UI elements
    await loadMerchantData();
    await loadConsumerData();
    await loadCustomer360();
    await loadComplianceQueue();
    await fetchAgentLogs();

    // Map drawing
    if (canvas) {
        setupMapPins();
        drawMap();
        canvas.addEventListener("click", handleMapClick);
    }
}

// -----------------------------------------------------------------------------
// NAVIGATION & STATE SYNC
// -----------------------------------------------------------------------------
function switchView(viewName) {
    // Hide all view sections
    document.querySelectorAll(".view-section").forEach(sec => sec.classList.remove("active"));
    // Show selected view section
    document.getElementById(`view-${viewName}`).classList.add("active");

    // Toggle nav active state
    document.querySelectorAll(".nav-btn").forEach(btn => btn.classList.remove("active"));
    document.getElementById(`btn-${viewName}`).classList.add("active");

    // Contextual redraws
    if (viewName === "consumer" && state.activePhoneTab === "nearby") {
        setTimeout(() => {
            drawMap();
        }, 100);
    } else if (viewName === "console") {
        fetchAgentLogs();
    }
}

function switchPhoneTab(tabName) {
    state.activePhoneTab = tabName;
    
    // Toggle active tab button
    document.querySelectorAll(".phone-tabs .tab-btn").forEach(btn => btn.classList.remove("active"));
    document.getElementById(`tab-${tabName === 'recommended' ? 'rec' : tabName === 'nearby' ? 'near' : 'trend'}`).classList.add("active");

    // Toggle content visible panes
    if (tabName === "nearby") {
        document.getElementById("phone-offers-feed").classList.add("hidden");
        document.getElementById("phone-map-container").classList.remove("hidden");
        // Canvas redrawing needs a minor delay to sync client dimensions
        setTimeout(() => drawMap(), 50);
    } else {
        document.getElementById("phone-map-container").classList.add("hidden");
        document.getElementById("phone-offers-feed").classList.remove("hidden");
        loadConsumerFeed();
    }
}

// Helper to fill selects
function populateDropdown(selectId, items, valueKey, labelKey) {
    const select = document.getElementById(selectId);
    if (!select) return;
    
    select.innerHTML = "";
    items.forEach(item => {
        const opt = document.createElement("option");
        opt.value = item[valueKey];
        opt.innerText = item[labelKey];
        select.appendChild(opt);
    });
}

// -----------------------------------------------------------------------------
// BACKEND API CLIENT CALLS
// -----------------------------------------------------------------------------
async function fetchMerchants() {
    try {
        const res = await fetch(`${API_BASE}/api/merchants`);
        state.merchants = await res.json();
    } catch (err) {
        console.error("Error fetching merchants", err);
    }
}

async function fetchConsumers() {
    try {
        const res = await fetch(`${API_BASE}/api/consumers`);
        state.customers = await res.json();
    } catch (err) {
        console.error("Error fetching consumers", err);
    }
}

// Load Selected Merchant Analytics & Settlement
async function loadMerchantData() {
    const merchantId = document.getElementById("merchant-select").value;
    if (!merchantId) return;
    state.selectedMerchantId = merchantId;

    try {
        const res = await fetch(`${API_BASE}/api/merchants/${merchantId}/analytics`);
        const data = await res.json();
        
        // Update stats
        document.getElementById("merchant-active-campaigns").innerText = data.metrics.campaigns_count;
        document.getElementById("merchant-driven-spend").innerText = `$${data.metrics.spend_driven.toFixed(2)}`;
        document.getElementById("merchant-cashback-paid").innerText = `$${data.metrics.cashback_paid.toFixed(2)}`;
        document.getElementById("merchant-roi").innerText = `${data.metrics.roi.toFixed(1)}x`;

        // Update list
        renderCampaignDirectory(data.campaigns);

        // Update billing
        renderBillingInvoices(data.settlements);
    } catch (err) {
        console.error("Error loading merchant analytics", err);
    }
}

// Load Consumer profile info & card rewards
async function loadConsumerData() {
    const customerId = document.getElementById("consumer-select").value;
    if (!customerId) return;
    state.selectedCustomerId = customerId;

    // Keep admin lookup select synced
    const adminSelect = document.getElementById("admin-customer-select");
    if (adminSelect && adminSelect.value !== customerId) {
        adminSelect.value = customerId;
    }

    try {
        const res = await fetch(`${API_BASE}/api/consumers/${customerId}`);
        const data = await res.json();
        const c = data.customer;

        document.getElementById("phone-user-name").innerText = c.name;
        document.getElementById("phone-cashback-value").innerText = `$${c.rewards.accumulated_cashback.toFixed(2)}`;
        document.getElementById("phone-redemptions-value").innerText = c.rewards.redemption_count;

        // Load feed
        await loadConsumerFeed();
    } catch (err) {
        console.error("Error loading consumer profile", err);
    }
}

// Helper to get browser geolocation coordinates with a timeout
function getDeviceLocation() {
    return new Promise((resolve) => {
        if (!navigator.geolocation) {
            resolve(null);
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
            () => resolve(null),
            { timeout: 1500 }
        );
    });
}

// Load Consumer Offers Feed based on active tab
async function loadConsumerFeed() {
    const customerId = state.selectedCustomerId;
    if (!customerId) return;

    try {
        const loc = await getDeviceLocation();
        let url = `${API_BASE}/api/consumers/${customerId}/offers`;
        if (loc) {
            url += `?latitude=${loc.lat}&longitude=${loc.lon}`;
        }
        const res = await fetch(url);
        const feeds = await res.json();
        
        let offers = [];
        if (state.activePhoneTab === "recommended") {
            offers = feeds.recommended;
        } else if (state.activePhoneTab === "trending") {
            offers = feeds.trending;
        }

        renderOffersFeed(offers);
    } catch (err) {
        console.error("Error loading consumer feed", err);
    }
}

// Load Customer 360 dashboard in Admin portal
async function loadCustomer360() {
    const customerId = document.getElementById("admin-customer-select").value;
    if (!customerId) return;

    try {
        const res = await fetch(`${API_BASE}/api/consumers/${customerId}`);
        const data = await res.json();
        const c = data.customer;
        const profile = data.affinity_profile;

        document.getElementById("c360-name").innerText = c.name;
        document.getElementById("c360-email").innerText = c.email;

        // Render affinities
        const affinitiesContainer = document.getElementById("c360-affinities");
        affinitiesContainer.innerHTML = "";
        
        profile.affinities.forEach(aff => {
            const pct = aff.score * 10;
            const affItem = document.createElement("div");
            affItem.className = "affinity-item";
            affItem.innerHTML = `
                <div class="affinity-label-row">
                    <span>${aff.category}</span>
                    <span>${aff.score.toFixed(1)} / 10.0</span>
                </div>
                <div class="affinity-bar-bg">
                    <div class="affinity-bar-fill" style="width: ${pct}%"></div>
                </div>
                <div class="affinity-explain">${aff.reasoning}</div>
            `;
            affinitiesContainer.appendChild(affItem);
        });

        // Render preferences
        const prefContainer = document.getElementById("c360-preferences");
        prefContainer.innerHTML = "";
        
        const prefs = [
            { label: "Personalization", val: c.preferences.personalization },
            { label: "Smart Notifications", val: c.preferences.notifications },
            { label: "Location Tracking", val: c.preferences.location }
        ];

        prefs.forEach(p => {
            const pill = document.createElement("span");
            pill.className = `pref-pill ${p.val ? 'active' : 'inactive'}`;
            pill.innerText = `${p.label}: ${p.val ? 'ON' : 'OFF'}`;
            prefContainer.appendChild(pill);
        });

        // Render transactions list
        const txContainer = document.getElementById("c360-transactions");
        txContainer.innerHTML = "";
        
        if (c.transactions.length === 0) {
            txContainer.innerHTML = `<div class="text-muted text-center italic py-2" style="font-size: 0.75rem;">No card swipes recorded.</div>`;
        } else {
            c.transactions.forEach(t => {
                const date = new Date(t.timestamp).toLocaleDateString();
                const time = new Date(t.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
                const txItem = document.createElement("div");
                txItem.className = "tx-history-item";
                txItem.innerHTML = `
                    <div>
                        <div class="tx-merchant">${t.merchant_name}</div>
                        <div class="tx-date">${date} ${time} | Category: ${t.category}</div>
                    </div>
                    <div class="tx-amt">$${t.amount.toFixed(2)}</div>
                `;
                txContainer.appendChild(txItem);
            });
        }

    } catch (err) {
        console.error("Error loading Customer 360", err);
    }
}

// Load Admin compliance manual queue
async function loadComplianceQueue() {
    try {
        const res = await fetch(`${API_BASE}/api/admin/compliance/pending`);
        const queue = await res.json();
        renderComplianceQueue(queue);
    } catch (err) {
        console.error("Error fetching compliance queue", err);
    }
}

// Load AI console log traces
async function fetchAgentLogs() {
    try {
        const res = await fetch(`${API_BASE}/api/admin/agent-logs`);
        const logs = await res.json();
        renderAgentLogs(logs);
    } catch (err) {
        console.error("Error loading agent logs", err);
    }
}

// -----------------------------------------------------------------------------
// RENDERING HELPERS
// -----------------------------------------------------------------------------
function renderCampaignDirectory(campaigns) {
    const list = document.getElementById("merchant-campaign-list");
    if (!list) return;

    list.innerHTML = "";
    if (campaigns.length === 0) {
        list.innerHTML = `<div class="text-muted italic text-center p-4">No campaigns built yet. Create one!</div>`;
        return;
    }

    campaigns.forEach(c => {
        const item = document.createElement("div");
        item.className = "campaign-item";
        
        let statusClass = "status-pending";
        if (c.status === "Active") statusClass = "status-active";
        else if (c.status === "Rejected") statusClass = "status-rejected";
        else if (c.status === "Completed") statusClass = "status-completed";

        const valLabel = c.offer_type === "Cashback Percentage" ? `${c.offer_value}%` : `$${c.offer_value}`;
        
        item.innerHTML = `
            <div class="campaign-item-header">
                <span class="campaign-item-name">${c.name}</span>
                <span class="status-badge ${statusClass}">${c.status}</span>
            </div>
            <p class="campaign-copy">${c.marketing_copy}</p>
            <div class="campaign-item-footer">
                <span>Value: <strong>${valLabel} Cashback</strong></span>
                <span>Remaining: <strong>$${c.remaining_budget.toFixed(0)}</strong> / $${c.budget.toFixed(0)}</span>
                <span>ROI: <strong>${c.roi}x</strong></span>
            </div>
        `;
        
        if (c.status === "Pending Compliance Review" && c.compliance_feedback) {
            item.innerHTML += `
                <div class="feedback-alert">
                    <strong>Review Warning:</strong> ${c.compliance_feedback}
                </div>
            `;
        }

        list.appendChild(item);
    });
}

function renderBillingInvoices(settlements) {
    const body = document.getElementById("merchant-billing-body");
    if (!body) return;

    body.innerHTML = "";
    if (settlements.length === 0) {
        body.innerHTML = `<tr><td colspan="6" class="text-center text-muted italic">No invoices settled yet. Swipe a card!</td></tr>`;
        return;
    }

    settlements.forEach(s => {
        const date = new Date(s.timestamp).toLocaleDateString();
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${date}</td>
            <td class="font-mono" style="font-size:0.75rem;">${s.redemption_id.slice(0,8)}...</td>
            <td class="text-red">$${s.cashback_charge.toFixed(2)}</td>
            <td class="text-green">$${s.bank_fee.toFixed(2)}</td>
            <td><strong>$${s.total_charged.toFixed(2)}</strong></td>
            <td><span class="pill pill-settled">Settled</span></td>
        `;
        body.appendChild(tr);
    });
}

function renderOffersFeed(offers) {
    const feed = document.getElementById("phone-offers-feed");
    if (!feed) return;

    feed.innerHTML = "";
    if (offers.length === 0) {
        feed.innerHTML = `<div class="text-muted text-center italic py-8" style="font-size:0.85rem;">No active offers match your segment criteria.</div>`;
        return;
    }

    offers.forEach(o => {
        const card = document.createElement("div");
        card.className = "phone-offer-card";
        
        const valLabel = o.offer_type === "Cashback Percentage" ? `${o.offer_value}%` : `$${o.offer_value}`;
        
        card.innerHTML = `
            <div class="offer-card-header">
                <span class="offer-card-merchant">${o.merchant_name}</span>
                <span class="offer-card-value">${valLabel} Cash Back</span>
            </div>
            <div class="offer-card-body">${o.marketing_copy}</div>
            <div class="offer-card-ai-explanation">✨ ${o.user_explanation}</div>
            <div class="offer-card-footer">
                <span class="offer-card-limits">Min spend: $${o.min_spend.toFixed(0)} | Cap: ${o.legal_disclosure.includes('Max') ? o.legal_disclosure.split('Max')[1].split('.')[0].trim() : '$5'}</span>
                <button class="btn-activate ${o.activated ? 'active' : ''}" onclick="toggleOfferActivation('${o.campaign_id}', ${o.activated})">
                    ${o.activated ? 'Activated ✓' : 'Link Card'}
                </button>
            </div>
        `;
        feed.appendChild(card);
    });
}

function renderComplianceQueue(queue) {
    const list = document.getElementById("compliance-list");
    if (!list) return;

    list.innerHTML = "";
    if (queue.length === 0) {
        list.innerHTML = `
            <div class="text-center p-8 text-muted italic">
                <div style="font-size:2rem; margin-bottom:0.5rem;">✨</div>
                Compliance queue is clear. No campaigns pending review.
            </div>`;
        return;
    }

    queue.forEach(c => {
        const item = document.createElement("div");
        item.className = "compliance-item-card";
        
        const date = new Date(c.created_at).toLocaleDateString();
        const valueStr = c.offer_type === "Cashback Percentage" ? `${c.offer_value}%` : `$${c.offer_value}`;

        item.innerHTML = `
            <div class="comp-meta-row">
                <span>Merchant: <strong>${c.merchant_name}</strong></span>
                <span>Date: ${date}</span>
            </div>
            <div class="comp-name">${c.name}</div>
            
            <div class="comp-copy-box">
                <strong>Copy:</strong> ${c.marketing_copy}
                <div class="comp-disclosure"><strong>Disclosure:</strong> ${c.legal_disclosure}</div>
            </div>
            
            <div class="comp-agent-feedback">
                <div class="comp-feedback-title">⚖️ Automated Compliance Audit (AG-008)</div>
                <div class="comp-feedback-text">${c.compliance_feedback || 'Flagged for restricted items.'}</div>
                <div class="comp-suggested-edit">
                    <strong>Suggested Copy Revision:</strong> "Get dining rewards on family meals at Starbucks instead."
                </div>
            </div>
            
            <div class="comp-actions">
                <button class="btn btn-green col" onclick="submitComplianceReview('${c.campaign_id}', true)">Approve & Launch</button>
                <button class="btn btn-secondary col" onclick="submitComplianceReview('${c.campaign_id}', false)">Reject Campaign</button>
            </div>
        `;
        list.appendChild(item);
    });
}

function renderAgentLogs(logs) {
    const stream = document.getElementById("agent-log-stream");
    if (!stream) return;

    stream.innerHTML = "";
    if (logs.length === 0) {
        stream.innerHTML = `<div class="text-muted italic text-center p-8">No AI Agent traces recorded yet. Generate a campaign or select customer to trigger.</div>`;
        return;
    }

    logs.forEach(l => {
        const item = document.createElement("div");
        item.className = "log-item";
        
        // Formatted pretty JSON
        let formattedInput = l.input;
        let formattedOutput = l.output;
        try {
            if (typeof l.input === 'object') formattedInput = JSON.stringify(l.input, null, 2);
            if (typeof l.output === 'object') formattedOutput = JSON.stringify(l.output, null, 2);
        } catch(e) {}

        item.innerHTML = `
            <div class="log-item-header">
                <span class="log-item-agent">${l.agent}</span>
                <span class="log-item-trace-id" style="font-family: monospace; font-size: 0.72rem; color: var(--success); margin-left: 10px; background: rgba(16, 185, 129, 0.1); padding: 0.1rem 0.4rem; border-radius: 4px;">Trace: ${l.trace_id || 'none'}</span>
                <span class="log-item-time" style="margin-left: auto;">${l.timestamp}</span>
            </div>
            <div class="log-payload-split">
                <div class="payload-block">
                    <div class="payload-label">Input Parameters</div>
                    <div class="payload-data">${formattedInput}</div>
                </div>
                <div class="payload-block">
                    <div class="payload-label">Agent Output Result</div>
                    <div class="payload-data">${formattedOutput}</div>
                </div>
            </div>
        `;

        stream.appendChild(item);
    });
}

// -----------------------------------------------------------------------------
// EVENT HANDLERS & ACTIONS
// -----------------------------------------------------------------------------
async function handleOnboard(event) {
    event.preventDefault();
    const name = document.getElementById("onboard-name").value;
    const category = document.getElementById("onboard-category").value;
    const address = document.getElementById("onboard-address").value;

    // Simulate coordinates in SF area
    const lat = 37.77 + Math.random() * 0.03;
    const lon = -122.42 + Math.random() * 0.04;

    try {
        const res = await fetch(`${API_BASE}/api/onboard/merchant`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, category, address, latitude: lat, longitude: lon })
        });
        
        const data = await res.json();
        if (data.status === "success") {
            alert(`Business onboarded successfully! Assigned ID: ${data.merchant.merchant_id}`);
            document.getElementById("onboard-form").reset();
            
            // Reload list & dropdowns
            await fetchMerchants();
            populateDropdown("merchant-select", state.merchants, "merchant_id", "name");
            
            // Select newly created merchant
            document.getElementById("merchant-select").value = data.merchant.merchant_id;
            await loadMerchantData();

            // Re-setup map pins
            setupMapPins();
            drawMap();
        }
    } catch(err) {
        console.error(err);
    }
}

async function handleCreateCampaign(event) {
    event.preventDefault();
    const merchantId = state.selectedMerchantId;
    const name = document.getElementById("camp-name").value;
    const offer_type = document.getElementById("camp-type").value;
    const offer_value = parseFloat(document.getElementById("camp-value").value);
    const min_spend = parseFloat(document.getElementById("camp-min-spend").value);
    const budget = parseFloat(document.getElementById("camp-budget").value);
    const duration_days = parseInt(document.getElementById("camp-duration").value);
    const marketing_copy = document.getElementById("camp-copy").value;
    const legal_disclosure = document.getElementById("camp-disclosure").value;

    // Grab checkboxes
    const segments = [];
    document.querySelectorAll("input[name='segments']:checked").forEach(cb => {
        segments.push(cb.value);
    });

    try {
        const res = await fetch(`${API_BASE}/api/merchants/${merchantId}/campaigns`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                merchant_id: merchantId, name, offer_type, offer_value, min_spend,
                budget, duration_days, audience_segments: segments, marketing_copy, legal_disclosure
            })
        });

        const data = await res.json();
        if (data.status === "success") {
            const compliant = data.compliance_review.is_compliant;
            if (compliant) {
                alert("Campaign approved by Compliance Agent! Launched live on Synq commerce network.");
            } else {
                alert("Campaign compliance review flagged! Sent to Bank Administrator Compliance Queue for manual review.");
            }

            document.getElementById("campaign-form").reset();
            await loadMerchantData();
            await loadComplianceQueue();
            await fetchAgentLogs();
        }
    } catch (err) {
        console.error(err);
    }
}

// AI SUGGESTION MODAL
function triggerAISuggestion() {
    document.getElementById("ai-modal").classList.add("active");
}

function closeAIModal() {
    document.getElementById("ai-modal").classList.remove("active");
}

async function generateAICampaign() {
    const goal = document.getElementById("ai-goal-select").value;
    const loader = document.getElementById("modal-loader");
    loader.classList.remove("hidden");

    try {
        const res = await fetch(`${API_BASE}/api/merchants/${state.selectedMerchantId}/ai-suggest`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({merchant_id: state.selectedMerchantId, goal})
        });
        
        const suggestion = await res.json();
        
        // Auto fill form
        document.getElementById("camp-name").value = suggestion.campaign_name;
        document.getElementById("camp-value").value = suggestion.offer_value;
        document.getElementById("camp-budget").value = suggestion.suggested_budget;
        document.getElementById("camp-duration").value = suggestion.suggested_duration_days;
        document.getElementById("camp-copy").value = suggestion.marketing_copy;
        document.getElementById("camp-disclosure").value = suggestion.suggested_legal_disclosure;

        // Set segments checkboxes
        document.querySelectorAll("input[name='segments']").forEach(cb => {
            cb.checked = suggestion.target_segments.includes(cb.value);
        });

        closeAIModal();
        alert("AI Agent Campaign Proposal generated and auto-filled. Review and submit!");
        await fetchAgentLogs();
    } catch (err) {
        console.error("AI Suggestion failed", err);
    } finally {
        loader.classList.add("hidden");
    }
}

// Offer Activation
async function toggleOfferActivation(campaignId, wasActivated) {
    const customerId = state.selectedCustomerId;
    const url = wasActivated ? "deactivate" : "activate";

    try {
        const res = await fetch(`${API_BASE}/api/consumers/${customerId}/offers/${url}`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({campaign_id: campaignId})
        });
        const data = await res.json();
        if (data.status === "success") {
            await loadConsumerData();
        }
    } catch(err) {
        console.error(err);
    }
}

// Simulate swiping transaction
async function handleSimulateTx(event) {
    event.preventDefault();
    const customerId = state.selectedCustomerId;
    const merchant_name = document.getElementById("sim-merchant").value;
    const amount = parseFloat(document.getElementById("sim-amount").value);
    
    const terminal = document.getElementById("tx-terminal");
    terminal.innerHTML = `<div class="terminal-line text-muted">&gt; Initializing card link scan...</div>`;

    try {
        const res = await fetch(`${API_BASE}/api/consumers/${customerId}/transactions/simulate`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({merchant_name, amount})
        });
        const result = await res.json();

        // Print steps to terminal with slight typewriter delay
        let index = 0;
        function printNextLine() {
            if (index < result.logs.length) {
                const line = result.logs[index];
                let cssClass = "text-muted";
                if (line.includes("Match Found")) cssClass = "text-success font-bold";
                if (line.includes("Settlement Billing")) cssClass = "text-success";
                
                terminal.innerHTML += `<div class="terminal-line ${cssClass}">&gt; ${line}</div>`;
                terminal.scrollTop = terminal.scrollHeight;
                index++;
                setTimeout(printNextLine, 500);
            } else {
                // Done printing logs, refresh balances
                loadConsumerData();
                loadCustomer360();
                loadMerchantData();
            }
        }
        setTimeout(printNextLine, 300);
    } catch(err) {
        terminal.innerHTML += `<div class="terminal-line text-error">&gt; Swipe Failure: Network server error processing transaction matching.</div>`;
    }
}

// Approve/Reject campaign in queue
async function submitComplianceReview(campaignId, approved) {
    let feedback = "";
    if (!approved) {
        feedback = prompt("Provide compliance rejection reasons (e.g. Restricted items):");
        if (feedback === null) return; // cancel
    }

    try {
        const res = await fetch(`${API_BASE}/api/admin/compliance/review`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({campaign_id: campaignId, approved, compliance_feedback: feedback})
        });
        const data = await res.json();
        if (data.status === "success") {
            alert(approved ? "Campaign approved and published!" : "Campaign rejected and returned to merchant draft box.");
            await loadComplianceQueue();
            await loadMerchantData();
        }
    } catch(err) {
        console.error(err);
    }
}

// -----------------------------------------------------------------------------
// LOCAL DEALS VECTOR MAP CANVAS
// -----------------------------------------------------------------------------
function setupMapPins() {
    // Coordinate bounding box for SF
    const latMin = 37.60, latMax = 37.82;
    const lonMin = -122.45, lonMax = -122.35;
    
    state.mapPins = state.merchants.map(m => {
        // Map latitude/longitude to canvas 0-100 dimensions
        const xPct = ((m.longitude - lonMin) / (lonMax - lonMin)) * 100;
        // Flip y because canvas starts at top left
        const yPct = (1.0 - ((m.latitude - latMin) / (latMax - latMin))) * 100;
        
        return {
            id: m.merchant_id,
            name: m.name,
            category: m.category,
            address: m.address,
            x: Math.max(10, Math.min(90, xPct)), // Clamp to avoid clipping borders
            y: Math.max(10, Math.min(90, yPct))
        };
    });
}

let activeMapFilter = "All";

function filterMap(category) {
    activeMapFilter = category;
    document.querySelectorAll(".map-filters .filter-chip").forEach(btn => {
        btn.classList.remove("active");
        if (btn.innerText === category) btn.classList.add("active");
    });
    drawMap();
}

function drawMap() {
    if (!ctx || !canvas) return;
    
    const w = canvas.width;
    const h = canvas.height;
    
    // Clear screen
    ctx.fillStyle = "#EEF0FA";
    ctx.fillRect(0, 0, w, h);
    
    // 1. Draw subtle grid
    ctx.strokeStyle = "rgba(99, 88, 210, 0.08)";
    ctx.lineWidth = 1;
    
    const gridSize = 20;
    for (let x = 0; x < w; x += gridSize) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
    }
    for (let y = 0; y < h; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
    }

    // 2. Draw glowing pins
    state.mapPins.forEach(p => {
        // Filter out if category doesn't match filter
        if (activeMapFilter !== "All" && p.category !== activeMapFilter) {
            return;
        }

        const cx = (p.x / 100) * w;
        const cy = (p.y / 100) * h;
        
        // Color based on category
        let color = "#8B5CF6"; // Purple default
        if (p.category === "Coffee") color = "#10B981"; // Green
        else if (p.category === "Dining") color = "#F43F5E"; // Coral
        else if (p.category === "Retail") color = "#3B82F6"; // Blue
        else if (p.category === "Grocery") color = "#F59E0B"; // Amber
        else if (p.category === "Entertainment") color = "#EC4899"; // Pink
        else if (p.category === "Electronics") color = "#06B6D4"; // Cyan
        else if (p.category === "Apparel") color = "#8B5CF6"; // Purple
        else if (p.category === "Gas & Automotive") color = "#10B981"; // Green
        else if (p.category === "Beauty & Wellness") color = "#D946EF"; // Fuchsia
        
        // Draw glow aura
        ctx.beginPath();
        ctx.arc(cx, cy, 12, 0, Math.PI * 2);
        ctx.fillStyle = color + "22"; // Translucent aura
        ctx.fill();
        
        // Draw core node
        ctx.beginPath();
        ctx.arc(cx, cy, 5, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.shadowColor = color;
        ctx.shadowBlur = 15;
        ctx.fill();
        
        // Reset shadow
        ctx.shadowBlur = 0;
        
        // Draw active selection ring
        if (state.selectedPin && state.selectedPin.id === p.id) {
            ctx.beginPath();
            ctx.arc(cx, cy, 9, 0, Math.PI * 2);
            ctx.strokeStyle = "rgba(55, 48, 163, 0.6)";
            ctx.lineWidth = 1.5;
            ctx.stroke();
        }

        // Draw node labels subtly
        ctx.fillStyle = "#4B5563";
        ctx.font = "8px Outfit";
        ctx.textAlign = "center";
        ctx.fillText(p.name, cx, cy - 10);
    });
}

async function handleMapClick(e) {
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;
    
    const w = canvas.width;
    const h = canvas.height;
    
    // Find closest pin
    let closest = null;
    let minDist = 25; // 25px max select range
    
    state.mapPins.forEach(p => {
        if (activeMapFilter !== "All" && p.category !== activeMapFilter) return;

        const px = (p.x / 100) * w;
        const py = (p.y / 100) * h;
        const dist = Math.sqrt((clickX - px) ** 2 + (clickY - py) ** 2);
        
        if (dist < minDist) {
            minDist = dist;
            closest = p;
        }
    });

    state.selectedPin = closest;
    drawMap();
    await renderMapDetailCard(closest);
}

async function renderMapDetailCard(pin) {
    const container = document.getElementById("map-pin-detail");
    if (!container) return;

    if (!pin) {
        container.innerHTML = `<div class="detail-placeholder">Tap a glowing map pin for store rewards</div>`;
        return;
    }

    try {
        // Fetch merchant campaigns
        const res = await fetch(`${API_BASE}/api/merchants/${pin.id}/analytics`);
        const data = await res.json();
        
        const activeCamps = data.campaigns.filter(c => c.status === "Active");
        
        if (activeCamps.length === 0) {
            container.innerHTML = `
                <div class="map-detail-card-content">
                    <div class="map-detail-title">${pin.name}</div>
                    <div class="map-detail-row" style="font-size:0.75rem; color:var(--text-muted);">
                        <span>Category: ${pin.category}</span>
                        <span>Address: ${pin.address}</span>
                    </div>
                    <div class="text-muted italic mt-1" style="font-size:0.75rem; text-align:center;">No card-linked rewards active right now.</div>
                </div>
            `;
            return;
        }

        // Render first active campaign
        const c = activeCamps[0];
        const valLabel = c.offer_type === "Cashback Percentage" ? `${c.offer_value}%` : `$${c.offer_value}`;
        
        const customerId = state.selectedCustomerId;
        const activatedIds = await (await fetch(`${API_BASE}/api/consumers/${customerId}/offers`)).json();
        const activated = activatedIds.recommended.some(o => o.campaign_id === c.campaign_id && o.activated);

        container.innerHTML = `
            <div class="map-detail-card-content">
                <div class="map-detail-row">
                    <div class="map-detail-title">${pin.name}</div>
                    <span style="font-size:0.75rem; color:var(--success); font-weight:800;">${valLabel} Cashback</span>
                </div>
                <div class="map-detail-row" style="font-size:0.7rem; color:var(--text-muted);">
                    <span>${pin.category} | ${pin.address}</span>
                    <span>Min spend: $${c.min_spend}</span>
                </div>
                <div style="font-size:0.75rem; line-height:1.3; color:#E5E7EB; margin-top:0.2rem;">${c.marketing_copy}</div>
                <div class="map-detail-row mt-2" style="margin-top:0.4rem; display:flex; justify-content:flex-end;">
                    <button class="btn-activate ${activated ? 'active' : ''}" onclick="toggleOfferActivation('${c.campaign_id}', ${activated})">
                        ${activated ? 'Activated ✓' : 'Link Card'}
                    </button>
                </div>
            </div>
        `;
    } catch(err) {
        console.error(err);
    }
}
