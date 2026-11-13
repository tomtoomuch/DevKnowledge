"use strict";

// Fixed DMZ-side probe: the frontend is not present on Supervisor's internal network.
async function checkFrontend(fetcher = fetch) {
    try {
        const response = await fetcher("http://frontend:80/health/frontend", {
            method: "GET", redirect: "manual",
            signal: AbortSignal.timeout(2500),
            headers: { Accept: "application/json" },
        });
        if (response.status !== 200) return false;
        const body = await response.text();
        if (body.length > 512) return false;
        const data = JSON.parse(body);
        return data && data.status === "ok" && data.service === "frontend";
    } catch {
        return false;
    }
}
module.exports = { checkFrontend };
