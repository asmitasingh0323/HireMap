import { io } from "socket.io-client";

// The Flask API base URL
export const API_BASE = "https://hiremap-ffey.onrender.com";

// One shared socket connection to the API for live streaming
export const socket = io(API_BASE, {
    transports: ["websocket", "polling"],
    autoConnect: true,
});

// Kick off a search. Results stream back over the socket, not this response.
export async function startSearch(keyword, location, deadline) {
    const resp = await fetch(`${API_BASE}/api/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keyword, location, deadline }),
    });
    return resp.json();
}