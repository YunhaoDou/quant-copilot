import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
const root=path.resolve(import.meta.dirname,"..");
const hash=crypto.createHash("sha256");
function visit(relative){const full=path.join(root,relative);if(!fs.existsSync(full))return;const s=fs.statSync(full);if(s.isDirectory()){for(const name of fs.readdirSync(full).sort())visit(path.join(relative,name));}else{hash.update(relative);hash.update("\0");if(relative==="tsconfig.json"){
 const config=JSON.parse(fs.readFileSync(full,"utf8"));
 config.include=(config.include||[]).filter(v=>!v.startsWith(".next"));
 hash.update(JSON.stringify(config));
}else hash.update(fs.readFileSync(full));}}
for(const name of ["app","components","lib","public","package.json","package-lock.json","next.config.mjs","tsconfig.json","tailwind.config.ts","postcss.config.js",".env",".env.local",".env.production"])visit(name);
for(const key of ["NEXT_PUBLIC_API_URL","NEXT_PUBLIC_CYCLE_API_URL"])hash.update(key+"="+(process.env[key]||""));
process.stdout.write(hash.digest("hex"));
