export function uploadPage(sessionId: string): Response {
  const nonce = crypto.randomUUID().replaceAll("-", "");
  const html = `<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="color-scheme" content="light dark">
  <title>Gửi file TikTok · Affiliate Report</title>
  <style nonce="${nonce}">
    :root{color-scheme:light dark;--bg:#f5f6f2;--surface:#fff;--ink:#17211e;--soft:#63706b;--line:#d7ddd9;--accent:#006d77;--on-accent:#fff;--ok:#18794e;--danger:#b42318;--focus:#006edc}
    @media(prefers-color-scheme:dark){:root{--bg:#111512;--surface:#1a201d;--ink:#f3f6f4;--soft:#a9b4af;--line:#35413b;--accent:#4fd1c5;--on-accent:#082326;--ok:#6ee7a0;--danger:#ff8a80;--focus:#72a7ff}}
    *{box-sizing:border-box}body{margin:0;min-height:100svh;padding:max(20px,env(safe-area-inset-top)) 18px max(28px,env(safe-area-inset-bottom));font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--ink)}
    main{width:min(100%,480px);margin:0 auto}.eyebrow{margin:0 0 8px;color:var(--accent);font-size:.76rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase}h1{margin:0;font-size:clamp(1.65rem,7vw,2.25rem);line-height:1.1}header p{margin:12px 0 22px;color:var(--soft)}
    .card{padding:20px;border:1px solid var(--line);border-radius:16px;background:var(--surface)}label{display:block;margin-bottom:8px;font-weight:750}.picker{display:grid;gap:10px;padding:18px;border:1px dashed var(--line);border-radius:14px}.picker input{width:100%;min-height:44px}.hint{margin:0;color:var(--soft);font-size:.9rem}
    button{width:100%;min-height:50px;margin-top:16px;border:0;border-radius:12px;padding:12px 16px;background:var(--accent);color:var(--on-accent);font:inherit;font-weight:800;cursor:pointer}button:disabled{cursor:wait;opacity:.55}button:focus-visible,input:focus-visible{outline:3px solid var(--focus);outline-offset:3px}
    progress{width:100%;height:10px;margin-top:16px}.status{min-height:52px;margin:16px 0 0;padding:13px 14px;border:1px solid var(--line);border-radius:12px;color:var(--soft)}.status[data-tone="ok"]{border-color:var(--ok);color:var(--ok)}.status[data-tone="danger"]{border-color:var(--danger);color:var(--danger)}.privacy{margin:18px 4px 0;color:var(--soft);font-size:.88rem}
    @media(max-width:360px){body{padding-inline:12px}.card{padding:16px}}
    @media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
  </style>
</head>
<body>
<main>
  <header><p class="eyebrow">Cloud Pairing</p><h1>Gửi file tới máy tính</h1><p>Chọn file Excel vừa xuất từ TikTok. File được mã hóa trên điện thoại trước khi gửi.</p></header>
  <section class="card" aria-labelledby="upload-title">
    <h2 id="upload-title">File TikTok (.xlsx)</h2>
    <div class="picker"><label for="file">Chọn một file tối đa 20 MB</label><input id="file" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"><p class="hint" id="file-hint">Mã ghép cặp dùng một lần và tự hết hạn sau 5 phút.</p></div>
    <button id="send" type="button">Mã hóa và gửi</button>
    <progress id="progress" max="100" value="0" hidden aria-label="Tiến độ gửi file"></progress>
    <p id="status" class="status" role="status" aria-live="polite">Đang kiểm tra mã ghép cặp…</p>
  </section>
  <p class="privacy">Cloudflare chỉ chuyển tiếp dữ liệu đã mã hóa. Khóa giải mã không được gửi lên cloud.</p>
</main>
<script nonce="${nonce}">
(() => {
  const sessionId=${JSON.stringify(sessionId)};
  const params=new URLSearchParams(location.hash.slice(1));
  const keyText=params.get('k')||'';
  const uploadToken=params.get('u')||'';
  history.replaceState(null,'',location.pathname);
  const fileInput=document.getElementById('file');
  const button=document.getElementById('send');
  const status=document.getElementById('status');
  const progress=document.getElementById('progress');
  const encoder=new TextEncoder();
  let usable=false;
  try{usable=decode64(keyText).byteLength===32&&/^[A-Za-z0-9_-]{40,64}$/.test(uploadToken);}catch{usable=false;}
  if(usable){status.textContent='Mã hợp lệ. Hãy chọn file Excel.';}else{status.textContent='Mã ghép cặp thiếu hoặc không hợp lệ. Hãy quét lại QR trên máy tính.';status.dataset.tone='danger';button.disabled=true;}
  button.addEventListener('click',async()=>{
    const file=fileInput.files&&fileInput.files[0];
    if(!file){show('Hãy chọn một file .xlsx.','danger');return;}
    if(!file.name.toLowerCase().endsWith('.xlsx')){show('Chỉ nhận file .xlsx.','danger');return;}
    if(file.size>20*1024*1024){show('File vượt quá 20 MB.','danger');return;}
    button.disabled=true;fileInput.disabled=true;progress.hidden=false;progress.value=8;show('Đang đọc và mã hóa file…');
    try{
      const metadata=encoder.encode(JSON.stringify({schema:1,filename:file.name,size:file.size,mime:file.type||'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}));
      if(metadata.byteLength>4096)throw new Error('Tên file quá dài.');
      const raw=new Uint8Array(await file.arrayBuffer());progress.value=30;
      const plain=new Uint8Array(4+metadata.byteLength+raw.byteLength);
      new DataView(plain.buffer).setUint32(0,metadata.byteLength,false);plain.set(metadata,4);plain.set(raw,4+metadata.byteLength);
      const iv=crypto.getRandomValues(new Uint8Array(12));
      const key=await crypto.subtle.importKey('raw',decode64(keyText),'AES-GCM',false,['encrypt']);
      const aad=encoder.encode('affiliate-report-pairing-v1:'+sessionId);
      const encrypted=new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:aad},key,plain));
      const body=new Uint8Array(iv.byteLength+encrypted.byteLength);body.set(iv);body.set(encrypted,iv.byteLength);progress.value=62;show('Đang gửi dữ liệu đã mã hóa…');
      const response=await fetch('/api/v1/sessions/'+encodeURIComponent(sessionId)+'/file',{method:'PUT',headers:{'authorization':'Pairing '+uploadToken,'content-type':'application/octet-stream'},body});
      const result=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(result?.error?.detail||'Không gửi được file.');
      progress.value=100;show('Đã gửi xong. Máy tính đang kiểm tra và nhập dữ liệu.','ok');button.textContent='Đã gửi';
    }catch(error){progress.hidden=true;show(error instanceof Error?error.message:'Gửi file thất bại.','danger');button.disabled=false;fileInput.disabled=false;}
  });
  function show(message,tone=''){status.textContent=message;if(tone)status.dataset.tone=tone;else delete status.dataset.tone;}
  function decode64(value){const normalized=value.replace(/-/g,'+').replace(/_/g,'/');const padded=normalized+'='.repeat((4-normalized.length%4)%4);const binary=atob(padded);return Uint8Array.from(binary,char=>char.charCodeAt(0));}
})();
</script>
</body>
</html>`;
  return new Response(html, {
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
      "content-security-policy": `default-src 'none'; script-src 'nonce-${nonce}'; style-src 'nonce-${nonce}'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`,
      "referrer-policy": "no-referrer",
      "permissions-policy": "camera=(), microphone=(), geolocation=()",
      "x-content-type-options": "nosniff",
      "x-frame-options": "DENY",
    },
  });
}
