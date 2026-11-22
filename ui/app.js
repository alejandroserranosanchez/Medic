const STORAGE_KEY = "medic.bookings";
const message = document.querySelector("#message");
const config = window.MEDIC_CONFIG || {};

function show(text, kind) {
  message.textContent = text;
  message.className = "message " + (kind || "");
}

function remember(booking) {
  const rows = remembered();
  const index = rows.findIndex((row) => row.id === booking.id);
  if (index >= 0) {
    rows[index] = { ...rows[index], ...booking };
  } else {
    rows.push(booking);
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(rows));
  renderBookings();
}

function remembered() {
  try {
    const rows = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(rows) ? rows : [];
  } catch (_error) {
    return [];
  }
}

function statusLabel(status) {
  return status || "unknown";
}

async function call(base, path, options) {
  let response;
  try {
    response = await fetch(base.replace(/\/$/, "") + path, {
      ...options,
      headers: { Accept: "application/json", ...(options && options.headers) },
    });
  } catch (_error) {
    throw new Error("The service could not be reached.");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.error || "HTTP " + response.status);
    error.status = response.status;
    error.body = body;
    throw error;
  }
  return { status: response.status, body };
}

function renderSessions(rows) {
  const body = document.querySelector("#sessions");
  body.replaceChildren();
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    [row.id, row.session_date, row.start_time + "–" + row.end_time, row.room_label, row.clinician_label]
      .forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        tr.append(cell);
      });
    tr.addEventListener("click", () => {
      document.querySelector("#booking-form [name=session_id]").value = row.id;
      const bookingStart = document.querySelector("#booking-form [name=start_time]");
      bookingStart.value = row.start_time;
      document.querySelector("#complete-form [name=performed_date]").value = row.session_date;
    });
    body.append(tr);
  });
}

function renderBookings() {
  const body = document.querySelector("#bookings");
  body.replaceChildren();
  remembered().forEach((row) => {
    const tr = document.createElement("tr");
    const status = document.createElement("span");
    status.className = "status " + (row.status || "");
    status.textContent = statusLabel(row.status);
    [row.id, row.patient_ref, row.procedure_code, row.session_date || ""].forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      tr.append(cell);
    });
    const statusCell = document.createElement("td");
    statusCell.append(status);
    const receivableCell = document.createElement("td");
    receivableCell.textContent = row.receivable_id || "";
    const action = document.createElement("td");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.textContent = "Use";
    button.addEventListener("click", () => {
      document.querySelector("#complete-form [name=booking_id]").value = row.id;
      if (row.session_date) {
        document.querySelector("#complete-form [name=performed_date]").value = row.session_date;
      }
      if (row.receivable_id) {
        document.querySelector("#receivable-form [name=receivable_id]").value = row.receivable_id;
      }
    });
    action.append(button);
    tr.append(statusCell, receivableCell, action);
    body.append(tr);
  });
}

function euros(cents) {
  if (typeof cents !== "number") return "—";
  const sign = cents < 0 ? "-" : "";
  return sign + (Math.abs(cents) / 100).toFixed(2) + " € (" + cents + " cents)";
}

async function loadSessions() {
  const result = await call(config.operationsUrl, "/sessions");
  renderSessions(result.body);
}

document.querySelector("#reload-sessions").addEventListener("click", () => {
  loadSessions().then(() => show("Sessions loaded.", "ok")).catch((error) => show(error.message, "err"));
});

document.querySelector("#session-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  call(config.operationsUrl, "/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      room_label: form.get("room_label"),
      clinician_label: form.get("clinician_label"),
      session_date: form.get("session_date"),
      start_time: form.get("start_time"),
      end_time: form.get("end_time"),
    }),
  })
    .then((result) => {
      show("Session " + result.body.id + " created.", "ok");
      return loadSessions();
    })
    .catch((error) => show(error.message, "err"));
});

document.querySelector("#booking-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const sessionId = Number(form.get("session_id"));
  const sessionDate = sessionDateFor(sessionId);
  call(config.operationsUrl, "/bookings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      start_time: form.get("start_time"),
      patient_ref: form.get("patient_ref"),
      procedure_code: form.get("procedure_code"),
      priority: Number(form.get("priority")),
      ready: form.get("ready") === "on",
      available_from: form.get("available_from"),
      available_to: form.get("available_to"),
      minimum_notice_minutes: Number(form.get("minimum_notice_minutes")),
    }),
  })
    .then((result) => {
      remember({
        id: result.body.id,
        patient_ref: result.body.patient_ref,
        procedure_code: result.body.procedure_code,
        session_date: sessionDate,
        status: result.body.status,
      });
      show("Booking " + result.body.id + " is " + result.body.status + ".", "ok");
    })
    .catch((error) => show(error.message, "err"));
});

function sessionDateFor(sessionId) {
  const rows = document.querySelectorAll("#sessions tr");
  for (const row of rows) {
    if (row.children[0] && Number(row.children[0].textContent) === sessionId) {
      return row.children[1].textContent;
    }
  }
  return "";
}

document.querySelector("#complete-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const bookingId = Number(form.get("booking_id"));
  call(config.operationsUrl, "/bookings/" + bookingId + "/complete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      performed_date: form.get("performed_date"),
      due_date: form.get("due_date"),
    }),
  })
    .then((result) => {
      remember({
        id: result.body.booking_id,
        status: result.body.status,
        receivable_id: result.body.receivable_id,
        procedure_code: result.body.procedure_code,
      });
      if (result.body.receivable_id) {
        document.querySelector("#receivable-form [name=receivable_id]").value = result.body.receivable_id;
      }
      const fee = typeof result.body.expected_fee_cents === "number"
        ? " Fee " + euros(result.body.expected_fee_cents) + "."
        : "";
      show(
        "Booking " + result.body.booking_id + " is completed (" + result.body.outcome + "). Receivable "
        + result.body.receivable_id + "." + fee,
        "ok",
      );
    })
    .catch((error) => {
      const bookingStatus = error.body && error.body.booking_status;
      if (bookingStatus) {
        remember({ id: bookingId, status: bookingStatus });
      }
      if (error.status === 503) {
        show(
          "HTTP 503. " + error.message + " Booking status: " + (bookingStatus || "not reported")
          + ". The completion was not confirmed. Send the same request again.",
          "err",
        );
        return;
      }
      show("HTTP " + (error.status || "") + ". " + error.message, "err");
    });
});

function loadReceivable(id) {
  return Promise.all([
    call(config.financeUrl, "/receivables/" + id),
    call(config.financeUrl, "/receivables/" + id + "/balance"),
  ]).then(([receivable, balance]) => {
    const row = receivable.body;
    const money = balance.body;
    document.querySelector("#receivable").textContent =
      "Receivable " + row.id + " for booking " + row.source_booking_id + ", " + row.procedure_code
      + ", performed " + row.performed_date + ", due " + row.due_date + ".\n"
      + "Expected " + euros(money.expected_fee_cents) + ". Paid " + euros(money.paid_cents)
      + ". Balance " + euros(money.balance_cents) + ".\n"
      + "Status " + money.status + ". Overdue: " + (money.overdue ? "yes" : "no")
      + " as of " + money.as_of + ".";
  });
}

document.querySelector("#receivable-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const id = Number(new FormData(event.target).get("receivable_id"));
  loadReceivable(id)
    .then(() => show("Receivable " + id + " loaded.", "ok"))
    .catch((error) => show(error.message, "err"));
});

document.querySelector("#payment-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const id = Number(document.querySelector("#receivable-form [name=receivable_id]").value);
  if (!id) {
    show("Load a receivable before recording a payment.", "err");
    return;
  }
  call(config.financeUrl, "/receivables/" + id + "/payments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      payment_reference: form.get("payment_reference"),
      amount_cents: Number(form.get("amount_cents")),
      paid_date: form.get("paid_date"),
    }),
  })
    .then((result) => {
      show(
        "Payment " + result.body.payment_reference + " recorded for "
        + euros(result.body.amount_cents) + " (HTTP " + result.status + ").",
        "ok",
      );
      return loadReceivable(id);
    })
    .catch((error) => show(error.message, "err"));
});

if (!config.operationsUrl || !config.financeUrl) {
  show("config.js must set operationsUrl and financeUrl.", "err");
} else {
  renderBookings();
  loadSessions().catch((error) => show(error.message, "err"));
}
