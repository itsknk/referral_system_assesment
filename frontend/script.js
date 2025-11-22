document.addEventListener("DOMContentLoaded", () => {

  // backend base URL config

  const baseUrlInput = document.getElementById("base-url-input");
  const baseUrlDisplay = document.getElementById("base-url-display");
  const useUrlBtn = document.getElementById("use-url-btn");

  let apiBaseUrl = (baseUrlInput && baseUrlInput.value.trim()) || "http://localhost:8000";

  function getApiBaseUrl() {
    return apiBaseUrl.replace(/\/+$/, ""); // strip trailing slash
  }

  if (baseUrlDisplay) {
    baseUrlDisplay.textContent = `Using: ${getApiBaseUrl()}`;
  }

  if (useUrlBtn) {
    useUrlBtn.addEventListener("click", () => {
      const val = baseUrlInput && baseUrlInput.value.trim();
      if (val) apiBaseUrl = val;
      if (baseUrlDisplay) {
        baseUrlDisplay.textContent = `Using: ${getApiBaseUrl()}`;
      }
    });
  }

  // helpers

  function setResult(preId, data) {
    const pre = document.getElementById(preId);
    if (!pre) return;
    pre.textContent = JSON.stringify(data, null, 2);
  }

  async function callApi(path, options = {}) {
    const url = `${getApiBaseUrl()}${path}`;
    const res = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });

    let payload;
    try {
      payload = await res.json();
    } catch (_) {
      payload = null;
    }

    if (!res.ok) {
      const msg =
        (payload && (payload.detail || payload.error || JSON.stringify(payload))) ||
        `Request failed (${res.status})`;
      throw new Error(msg);
    }

    return payload;
  }

  // generate referral code
  // POST /api/referral/generate

  const genUserIdInput = document.getElementById("generate-user-id");
  const genButton = document.getElementById("generate-button");

  if (genButton) {
    genButton.addEventListener("click", async () => {
      const raw = genUserIdInput && genUserIdInput.value.trim();
      if (!raw) return alert("Please enter a user ID");

      const userId = Number(raw);
      if (Number.isNaN(userId)) return alert("User ID must be a number");

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

  // register referral
  // POST /api/referral/register

  const regChildIdInput = document.getElementById("register-child-id");
  const regCodeInput = document.getElementById("register-referral-code");
  const regButton = document.getElementById("register-button");

  if (regButton) {
    regButton.addEventListener("click", async () => {
      const rawChild = regChildIdInput && regChildIdInput.value.trim();
      const rawCode = regCodeInput && regCodeInput.value.trim();

      if (!rawChild) return alert("Please enter child user ID");
      if (!rawCode) return alert("Please enter referral code");

      const childId = Number(rawChild);
      if (Number.isNaN(childId)) return alert("Child user ID must be a number");

      try {
        const data = await callApi("/api/referral/register", {
          method: "POST",
          body: JSON.stringify({
            child_user_id: childId,
            referral_code: rawCode,
          }),
        });
        setResult("response-output", data);
      } catch (e) {
        alert(e.message || "Failed to register referral");
      }
    });
  }

  // submit trade
  // POST /api/webhook/trade

  const tradeIdInput = document.getElementById("trade-id");
  const traderIdInput = document.getElementById("trade-trader-id");
  const chainInput = document.getElementById("trade-chain");
  const feeTokenInput = document.getElementById("trade-fee-token");
  const feeAmountInput = document.getElementById("trade-fee-amount");
  const executedAtInput = document.getElementById("trade-executed-at");
  const tradeButton = document.getElementById("trade-button");

  if (tradeButton) {
    tradeButton.addEventListener("click", async () => {
      const tradeId = tradeIdInput && tradeIdInput.value.trim();
      const traderRaw = traderIdInput && traderIdInput.value.trim();
      const feeRaw = feeAmountInput && feeAmountInput.value.trim();

      if (!tradeId) return alert("Please enter trade ID");
      if (!traderRaw) return alert("Please enter trader user ID");
      if (!feeRaw) return alert("Please enter fee amount");

      const traderId = Number(traderRaw);
      if (Number.isNaN(traderId)) return alert("Trader user ID must be a number");

      const feeAmount = Number(feeRaw);
      if (Number.isNaN(feeAmount)) return alert("Fee amount must be a number");

      const chain = (chainInput && chainInput.value.trim()) || "arbitrum";
      const feeToken = (feeTokenInput && feeTokenInput.value.trim()) || "USDC";
      const executedAt =
        (executedAtInput && executedAtInput.value.trim()) ||
        new Date().toISOString();

      try {
        const data = await callApi("/api/webhook/trade", {
          method: "POST",
          body: JSON.stringify({
            trade_id: tradeId,
            trader_id: traderId,
            chain,
            fee_token: feeToken,
            fee_amount: feeAmount.toFixed(6), // backend expects Decimal-like string
            executed_at: executedAt,
          }),
        });
        setResult("response-output", data);
      } catch (e) {
        alert(e.message || "Failed to submit trade");
      }
    });
  }

  // view referral network
  // GET /api/referral/network

  const networkRootInput = document.getElementById("network-root-id");
  const networkMaxLevelsInput = document.getElementById("network-max-levels");
  const networkButton = document.getElementById("network-button");

  if (networkButton) {
    networkButton.addEventListener("click", async () => {
      const rootRaw = networkRootInput && networkRootInput.value.trim();
      if (!rootRaw) return alert("Please enter root user ID");

      const rootId = Number(rootRaw);
      if (Number.isNaN(rootId)) return alert("Root user ID must be a number");

      const maxLevels =
        (networkMaxLevelsInput && Number(networkMaxLevelsInput.value)) || 3;

      try {
        const data = await callApi(
          `/api/referral/network?root_user_id=${rootId}&max_levels=${maxLevels}`,
          { method: "GET" }
        );
        setResult("response-output", data);
      } catch (e) {
        alert(e.message || "Failed to fetch network");
      }
    });
  }

  // view earnings
  // GET /api/referral/earnings

  const earningsUserIdInput = document.getElementById("earnings-user-id");
  const earningsBreakdownInput = document.getElementById(
    "earnings-include-breakdown"
  );
  const earningsFromInput = document.getElementById("earnings-from");
  const earningsToInput = document.getElementById("earnings-to");
  const earningsButton = document.getElementById("earnings-button");

  if (earningsButton) {
    earningsButton.addEventListener("click", async () => {
      const userRaw = earningsUserIdInput && earningsUserIdInput.value.trim();
      if (!userRaw) return alert("Please enter user ID");

      const userId = Number(userRaw);
      if (Number.isNaN(userId)) return alert("User ID must be a number");

      const includeBreakdown = !!(
        earningsBreakdownInput && earningsBreakdownInput.checked
      );
      const fromVal = earningsFromInput && earningsFromInput.value.trim();
      const toVal = earningsToInput && earningsToInput.value.trim();

      const params = new URLSearchParams({
        user_id: userId,
        include_breakdown: includeBreakdown ? "true" : "false",
      });
      if (fromVal) params.set("from", fromVal);
      if (toVal) params.set("to", toVal);

      try {
        const data = await callApi(`/api/referral/earnings?${params.toString()}`, {
          method: "GET",
        });
        setResult("response-output", data);
      } catch (e) {
        alert(e.message || "Failed to fetch earnings");
      }
    });
  }

  // claim preview (UI-only)
  // POST /api/referral/claim

  const claimUserIdInput = document.getElementById("claim-user-id");
  const claimTokenInput = document.getElementById("claim-token");
  const claimButton = document.getElementById("claim-button");

  if (claimButton) {
    claimButton.addEventListener("click", async () => {
      const userRaw = claimUserIdInput && claimUserIdInput.value.trim();
      if (!userRaw) return alert("Please enter user ID");

      const userId = Number(userRaw);
      if (Number.isNaN(userId)) return alert("User ID must be a number");

      const token = (claimTokenInput && claimTokenInput.value.trim()) || "USDC";

      try {
        const data = await callApi("/api/referral/claim", {
          method: "POST",
          body: JSON.stringify({ user_id: userId, token }),
        });
        setResult("response-output", data);
      } catch (e) {
        alert(e.message || "Failed to preview claim");
      }
    });
  }

  // new addon #1: create user
  // POST /api/user/create

  const createUsernameInput = document.getElementById("create-username");
  const createUserButton = document.getElementById("create-user-button");

  if (createUserButton) {
    createUserButton.addEventListener("click", async () => {
      const username =
        createUsernameInput && createUsernameInput.value.trim();
      if (!username) return alert("Please enter a username");

      try {
        const data = await callApi("/api/user/create", {
          method: "POST",
          body: JSON.stringify({ username }),
        });
        setResult("response-output", data);
      } catch (e) {
        alert(e.message || "Failed to create user");
      }
    });
  }

  // new addon #2: execute claim (real processing)
  // POST /api/referral/claim/execute

  const claimExecUserIdInput = document.getElementById("claim-exec-user-id");
  const claimExecTokenInput = document.getElementById("claim-exec-token");
  const claimExecButton = document.getElementById("claim-exec-button");

  if (claimExecButton) {
    claimExecButton.addEventListener("click", async () => {
      const userRaw =
        claimExecUserIdInput && claimExecUserIdInput.value.trim();
      if (!userRaw) return alert("Please enter user ID");

      const userId = Number(userRaw);
      if (Number.isNaN(userId)) return alert("User ID must be a number");

      const token =
        (claimExecTokenInput && claimExecTokenInput.value.trim()) || "USDC";

      try {
        const data = await callApi("/api/referral/claim/execute", {
          method: "POST",
          body: JSON.stringify({ user_id: userId, token }),
        });
        setResult("response-output", data);
      } catch (e) {
        alert(e.message || "Failed to execute claim");
      }
    });
  }
});
