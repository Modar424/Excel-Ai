// Post-build: copy public/_headers into dist/ with connect-src pinned to the exact API origin.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
const api = process.env.VITE_API_BASE_URL || "";
let text = readFileSync("public/_headers", "utf8");
let origin = "";
try { origin = new URL(api).origin; } catch { /* keep wildcard */ }
if (origin && origin.startsWith("https://")) text = text.replace("https://*.onrender.com", origin);
else console.warn("write-headers: VITE_API_BASE_URL not an https URL; CSP keeps https://*.onrender.com");
if (!existsSync("dist")) throw new Error("dist/ missing");
writeFileSync("dist/_headers", text);
console.log("write-headers: connect-src ->", origin || "https://*.onrender.com");
