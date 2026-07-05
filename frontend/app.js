const chatMessages = document.getElementById("chatMessages");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const resetBtn = document.getElementById("resetBtn");

function newSessionId() {
    return "sess-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

let sessionId = sessionStorage.getItem("hospital_session_id");
if (!sessionId) {
    sessionId = newSessionId();
    sessionStorage.setItem("hospital_session_id", sessionId);
}

function addMessage(text, role) {
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    div.textContent = text;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return div;
}

/** Render small colored pills for each agent in the trace, ABOVE the message. */
function addAgentTrace(trace) {
    if (!trace || trace.length === 0) return;
    const row = document.createElement("div");
    row.className = "agent-trace";
    trace.forEach(({ agent, action }) => {
        const pill = document.createElement("span");
        pill.className = "agent-pill";
        pill.title = action || agent;
        pill.textContent = agent;
        row.appendChild(pill);
    });
    chatMessages.appendChild(row);
}

/** Render a structured result card (appointment / lab / notification). */
function addResultCard(card) {
    if (!card) return;

    const statuses = [
        { key: "appointment_status", label: "Appointment", icon: "🗓" },
        { key: "lab_test_status",    label: "Lab Test",    icon: "🔬" },
        { key: "notification_status",label: "Notification",icon: "🔔" },
    ];

    const wrapper = document.createElement("div");
    wrapper.className = "result-card";

    statuses.forEach(({ key, label, icon }) => {
        const val = card[key];
        if (!val || val === "Not requested" || val === "Pending") return;

        const row = document.createElement("div");
        row.className = "result-row";

        const isBooked  = typeof val === "string" && val.toLowerCase().startsWith("booked");
        const isSuccess = typeof val === "string" && (
            val.toLowerCase().startsWith("scheduled") ||
            val.toLowerCase().startsWith("sent") ||
            val.toLowerCase().startsWith("report") ||
            val.toLowerCase().includes("success")
        );
        const isFailed  = typeof val === "string" && (
            val.toLowerCase().startsWith("failed") ||
            val.toLowerCase().startsWith("no booking") ||
            val.toLowerCase().startsWith("no lab") ||
            val.toLowerCase().startsWith("not sent")
        );

        const dot = document.createElement("span");
        dot.className = "result-dot " + (isBooked || isSuccess ? "dot-ok" : isFailed ? "dot-fail" : "dot-info");

        const labelEl = document.createElement("span");
        labelEl.className = "result-label";
        labelEl.textContent = `${icon} ${label}:`;

        const valueEl = document.createElement("span");
        valueEl.className = "result-value";
        valueEl.textContent = val;

        row.appendChild(dot);
        row.appendChild(labelEl);
        row.appendChild(valueEl);
        wrapper.appendChild(row);
    });

    if (card.summary) {
        const sumEl = document.createElement("div");
        sumEl.className = "result-summary";
        sumEl.textContent = card.summary;
        wrapper.appendChild(sumEl);
    }

    if (wrapper.childElementCount > 0) {
        chatMessages.appendChild(wrapper);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}

function showTyping() {
    const div = document.createElement("div");
    div.className = "typing";
    div.id = "typingIndicator";
    div.innerHTML = "<span></span><span></span><span></span>";
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function hideTyping() {
    const el = document.getElementById("typingIndicator");
    if (el) el.remove();
}

async function loadGreeting() {
    try {
        const res = await fetch("/api/chat/greeting");
        const data = await res.json();
        addMessage(data.reply, "bot");
    } catch (e) {
        addMessage("Hello! How can I help you today?", "bot");
    }
}

async function sendMessage(text) {
    addMessage(text, "user");
    sendBtn.disabled = true;
    showTyping();

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId, message: text }),
        });
        hideTyping();
        if (!res.ok) throw new Error(`Server error: ${res.status}`);
        const data = await res.json();

        // 1. Show agent pills
        if (data.agent_trace && data.agent_trace.length > 0) {
            addAgentTrace(data.agent_trace);
        }

        // 2. Show result card immediately (before the prose reply)
        if (data.result_card) {
            addResultCard(data.result_card);
        }

        // 3. Show the bot's prose reply
        addMessage(data.reply, "bot");

    } catch (err) {
        hideTyping();
        addMessage("Sorry, something went wrong. Please try again.", "bot");
        console.error(err);
    } finally {
        sendBtn.disabled = false;
        messageInput.focus();
    }
}

chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = messageInput.value.trim();
    if (!text) return;
    messageInput.value = "";
    messageInput.style.height = "auto";
    sendMessage(text);
});

// Enter to send, Shift+Enter for newline; auto-grow textarea.
messageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        chatForm.requestSubmit();
    }
});
messageInput.addEventListener("input", () => {
    messageInput.style.height = "auto";
    messageInput.style.height = messageInput.scrollHeight + "px";
});

resetBtn.addEventListener("click", () => {
    sessionId = newSessionId();
    sessionStorage.setItem("hospital_session_id", sessionId);
    chatMessages.innerHTML = "";
    loadGreeting();
});

const dbContent = document.getElementById("dbContent");
const refreshDbBtn = document.getElementById("refreshDbBtn");

async function loadDatabaseData() {
    try {
        dbContent.innerHTML = "<p>Loading data...</p>";
        const res = await fetch("/api/database");
        if (!res.ok) throw new Error("Failed to load database data");
        const data = await res.json();
        
        dbContent.innerHTML = "";
        
        for (const [tableName, rows] of Object.entries(data)) {
            const wrapper = document.createElement("div");
            wrapper.className = "db-table-wrapper";
            
            const title = document.createElement("h3");
            title.textContent = tableName.replace("_", " ");
            wrapper.appendChild(title);
            
            if (rows.length === 0) {
                const empty = document.createElement("p");
                empty.textContent = "No data found.";
                wrapper.appendChild(empty);
            } else {
                const table = document.createElement("table");
                table.className = "db-table";
                
                const thead = document.createElement("thead");
                const trHead = document.createElement("tr");
                const keys = Object.keys(rows[0]);
                keys.forEach(key => {
                    const th = document.createElement("th");
                    th.textContent = key;
                    trHead.appendChild(th);
                });
                thead.appendChild(trHead);
                table.appendChild(thead);
                
                const tbody = document.createElement("tbody");
                rows.forEach(row => {
                    const tr = document.createElement("tr");
                    keys.forEach(key => {
                        const td = document.createElement("td");
                        td.textContent = row[key] !== null ? row[key] : "";
                        tr.appendChild(td);
                    });
                    tbody.appendChild(tr);
                });
                table.appendChild(tbody);
                
                wrapper.appendChild(table);
            }
            
            dbContent.appendChild(wrapper);
        }
    } catch (e) {
        dbContent.innerHTML = `<p style="color: red;">Error: ${e.message}</p>`;
    }
}

refreshDbBtn.addEventListener("click", loadDatabaseData);

// Also refresh database on sending a message to see updates immediately
const originalSendMessage = sendMessage;
sendMessage = async (text) => {
    await originalSendMessage(text);
    loadDatabaseData();
}

loadGreeting();
loadDatabaseData();
