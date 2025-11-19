// ---------- Config ----------

// default API base; overridden when user hits "Use this URL"
let apiBaseUrl = "http://localhost:8000";

// helper to safely read base URL input
function getApiBaseUrl() {
  const input = document.getElementById("api-base-url-input");
  const value = input && input.value.trim();
  return value || apiBaseUrl;
}

// generic API caller
async function callApi(path, options = {}) {
  const base = getApiBaseUrl().replace(/\/+$/, "");
  const url = `${base}${path}`;

  const merged = {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  };

  try {
    const res = await fetch(url, merged);
    let body = null;
    try {
      body = await res.json();
    } catch {
      // ignore JSON errors for empty bodies
    }

    if (!res.ok) {
      const msg =
        (body && body.detail) ||
        `Request failed: ${res.status} ${res.statusText}`;
      throw new Error(msg);
    }

    return body;
  } catch (err) {
    console.error("API call failed", err);
    throw err;
  }
}

function setResult(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  if (typeof value === "string") {
    el.textContent = value;
  } else {
    el.textContent = JSON.stringify(value, null, 2);
  }
}

// ---------- wire up once DOM is ready ----------

document.addEventListener("DOMContentLoaded", () => {
  // Backend config
  const baseUrlInput = document.getElementById("api-base-url-input");
  const useUrlBtn = document.getElementById("api-base-url-button");
  const baseUrlDisplay = document.getElementById("api-base-url-display");

  if (useUrlBtn) {
    useUrlBtn.addEventListener("click", () => {
      const val = baseUrlInput && baseUrlInput.value.trim();
      if (val) apiBaseUrl = val;
      if (baseUrlDisplay) {
        baseUrlDisplay.textContent = `Using: ${getApiBaseUrl()}`;
      }
    });
  }

  // ---------- generate referral code (POST /api/referral/generate) ----------

  const genUserIdInput = document.getElementById("generate-user-id");
  const genButton = document.getElementById("generate-button");

  if (genButton) {
    genButton.addEventListener("click", async () => {
      if (!genUserIdInput || !genUserIdInput.value.trim()) {
        alert("Please enter a user ID");
        return;
      }

      const userId = Number(genUserIdInput.value.trim());
      if (Number.isNaN(userId)) {
        alert("User ID must be a number");
        return;
      }

      try {
        const data = await callApi("/api/referral/generate", {
          method: "POST", 
          body: JSON.stringify({ user_id: userId }),
        });
        setResult("response-output", data);
      } catch (e) {
        alert(e.message || "Failed to generate referral code");
      }
    });
  }

  // ---------- register referral (POST /api/referral/register) ----------

  const regChildIdInput = document.getElementById("register-child-id");
  const regCodeInput = document.getElementById("register-referral-code");
  const regButton = document.getElementById("register-button");

  if (regButton) {
    regButton.addEventListener("click", async () => {
      if (!regChildIdInput || !regChildIdInput.value.trim()) {
        alert("Please enter child user ID");
        return;
      }
      if (!regCodeInput || !regCodeInput.value.trim()) {
        alert("Please enter referral code");
        return;
      }

      const childId = Number(regChildIdInput.value.trim());
      const code = regCodeInput.value.trim();

      if (Number.isNaN(childId)) {
        alert("Child user ID must be a number");
        return;
      }

      try {
        const data = await callApi("/api/referral/register", {
          method: "POST",
          body: JSON.stringify({
            child_user_id: childId,
            referral_code: code,
          }),
        });
        setResult("response-output", data);
      } catch (e) {
        alert(e.message || "Failed to register referral");
      }
    });
  }

  // ---------- submit trade (POST /api/webhook/trade) ----------

  const tradeIdInput = document.getElementById("trade-id");
  const traderIdInput = document.getElementById("trade-trader-id");
  const chainInput = document.getElementById("trade-chain");
  const feeTokenInput = document.getElementById("trade-fee-token");
  const feeAmountInput = document.getElementById("trade-fee-amount");
  const executedAtInput = document.getElementById("trade-executed-at");
  const tradeButton = document.getElementById("trade-button");

  if (tradeButton) {
    tradeButton.addEventListener("click", async () => {
      if (!tradeIdInput || !tradeIdInput.value.trim()) {
        alert("Please enter trade ID");
        return;
      }
      if (!traderIdInput || !traderIdInput.value.trim()) {
        alert("Please enter trader user ID");
        return;
      }
      if (!feeAmountInput || !feeAmountInput.value.trim()) {
        alert("Please enter fee amount");
        return;
      }

      const traderId = Number(traderIdInput.value.trim());
      if (Number.isNaN(traderId)) {
        alert("Trader user ID must be a number");
        return;
      }

      const body = {
        trade_id: tradeIdInput.value.trim(),
        trader_id: traderId,
        chain: (chainInput && chainInput.value.trim()) || "arbitrum",
        fee_token: (feeTokenInput && feeTokenInput.value.trim()) || "USDC",
        fee_amount: feeAmountInput.value.trim(),
        executed_at:
          (executedAtInput && executedAtInput.value.trim()) ||
          new Date().toISOString(),
      };

      try {
        const data = await callApi("/api/webhook/trade", {
          method: "POST",
          body: JSON.stringify(body),
        });
        setResult("response-output", data);
      } catch (e) {
        alert(e.message || "Failed to submit trade");
      }
    });
  }

  // ---------- view referral network (GET /api/referral/network) ----------

  const netRootIdInput = document.getElementById("network-root-id");
  const netMaxLevelsInput = document.getElementById("network-max-levels");
  const netLimitInput = document.getElementById("network-limit");
  const netButton = document.getElementById("network-button");

  if (netButton) {
    netButton.addEventListener("click", async () => {
      if (!netRootIdInput || !netRootIdInput.value.trim()) {
        alert("Please enter root user ID");
        return;
      }

      const rootId = Number(netRootIdInput.value.trim());
      if (Number.isNaN(rootId)) {
        alert("Root user ID must be a number");
        return;
      }

      const maxLevels = Number(
        (netMaxLevelsInput && netMaxLevelsInput.value.trim()) || "3"
      );
      const limit = Number(
        (netLimitInput && netLimitInput.value.trim()) || "50"
      );

      const params = new URLSearchParams({
        user_id: String(rootId),
        max_levels: String(maxLevels),
        limit_per_level: String(limit),
      });

      try {
        const data = await callApi(`/api/referral/network?${params.toString()}`);
        setResult("response-output", data);
      } catch (e) {
        alert(e.message || "Failed to fetch network");
      }
    });
  }

  // ---------- view earnings (GET /api/referral/earnings) ----------

  const earnUserIdInput = document.getElementById("earnings-user-id");
  const earnIncludeBreakdownInput = document.getElementById(
    "earnings-include-breakdown"
  );
  const earnFromInput = document.getElementById("earnings-from");
  const earnToInput = document.getElementById("earnings-to");
  const earnLimitInput = document.getElementById("earnings-breakdown-limit");
  const earnButton = document.getElementById("earnings-button");

  if (earnButton) {
    earnButton.addEventListener("click", async () => {
      if (!earnUserIdInput || !earnUserIdInput.value.trim()) {
        alert("Please enter user ID");
        return;
      }

      const userId = Number(earnUserIdInput.value.trim());
      if (Number.isNaN(userId)) {
        alert("User ID must be a number");
        return;
      }

      const params = new URLSearchParams({
        user_id: String(userId),
      });

      if (earnIncludeBreakdownInput && earnIncludeBreakdownInput.checked) {
        params.set("include_breakdown", "true");
        const lim = Number(
          (earnLimitInput && earnLimitInput.value.trim()) || "50"
        );
        params.set("breakdown_limit", String(lim));
      }

      if (earnFromInput && earnFromInput.value.trim()) {
        params.set("from", earnFromInput.value.trim());
      }
      if (earnToInput && earnToInput.value.trim()) {
        params.set("to", earnToInput.value.trim());
      }

      try {
        const data = await callApi(
          `/api/referral/earnings?${params.toString()}`
        );
        setResult("response-output", data);
      } catch (e) {
        alert(e.message || "Failed to fetch earnings");
      }
    });
  }

  // ---------- claim preview (UI only, POST /api/referral/claim) ----------

  const claimUserIdInput = document.getElementById("claim-user-id");
  const claimTokenInput = document.getElementById("claim-token");
  const claimButton = document.getElementById("claim-button");

  if (claimButton) {
    claimButton.addEventListener("click", async () => {
      if (!claimUserIdInput || !claimUserIdInput.value.trim()) {
        alert("Please enter user ID");
        return;
      }

      const userId = Number(claimUserIdInput.value.trim());
      if (Number.isNaN(userId)) {
        alert("User ID must be a number");
        return;
      }

      const token =
        (claimTokenInput && claimTokenInput.value.trim()) || "USDC";

      try {
        const data = await callApi("/api/referral/claim", {
          method: "POST",
          body: JSON.stringify({
            user_id: userId,
            token,
          }),
        });
        setResult("response-output", data);
      } catch (e) {
        alert(e.message || "No claimable amount or claim check failed");
      }
    });
  }
});

