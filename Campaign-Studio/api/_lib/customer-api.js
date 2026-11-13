import { db, json, requireUser, sha } from './core.js';
import { randomBytes } from 'node:crypto';

export async function issueApiKey(req,res) {
  const sql=db(), user=await requireUser(req,res,sql); if(!user) return;
  const name=String(req.body?.name||'Default key').trim();
  if(!name||name.length>80) return json(res,400,{error:'Key name must be 1–80 characters.'});
  const raw='cst_live_'+randomBytes(32).toString('base64url');
  const rows=await sql`INSERT INTO customer_api_keys(user_id,name,key_prefix,key_hash) VALUES(${user.id},${name},${raw.slice(0,20)},${sha(raw)}) RETURNING id,name,key_prefix,created_at`;
  return json(res,201,{api_key:raw,key:rows[0],warning:'Copy this key now. It will not be shown again.'});
}
export async function listApiKeys(req,res) {
  const sql=db(), user=await requireUser(req,res,sql); if(!user) return;
  const keys=await sql`SELECT id,name,key_prefix,created_at,last_used_at,revoked_at FROM customer_api_keys WHERE user_id=${user.id} ORDER BY created_at DESC LIMIT 50`;
  return json(res,200,{keys});
}
export async function revokeApiKey(req,res) {
  const sql=db(), user=await requireUser(req,res,sql); if(!user) return;
  const id=Number(req.query?.id); if(!Number.isSafeInteger(id)||id<1) return json(res,400,{error:'Invalid key id.'});
  const rows=await sql`UPDATE customer_api_keys SET revoked_at=now() WHERE id=${id} AND user_id=${user.id} AND revoked_at IS NULL RETURNING id`;
  if(!rows.length) return json(res,404,{error:'Active API key not found.'});
  return json(res,200,{ok:true});
}
export async function authenticateApiKey(req,res) {
  const auth=String(req.headers.authorization||'');
  if(!auth.startsWith('Bearer cst_live_')) { json(res,401,{error:'A valid Campaign Studio API key is required.'}); return null; }
  const sql=db(), token=auth.slice(7);
  const rows=await sql`SELECT id,user_id FROM customer_api_keys WHERE key_hash=${sha(token)} AND revoked_at IS NULL LIMIT 1`;
  if(!rows.length) { json(res,401,{error:'Invalid or revoked API key.'}); return null; }
  const key=rows[0];
  const usage=await sql`INSERT INTO api_usage_daily(user_id,usage_date,request_count) VALUES(${key.user_id},CURRENT_DATE,1)
    ON CONFLICT(user_id,usage_date) DO UPDATE SET request_count=api_usage_daily.request_count+1 RETURNING request_count`;
  const used=Number(usage[0]?.request_count||0), limit=Math.max(1,Number(process.env.API_DAILY_REQUEST_LIMIT||100));
  if(used>limit) { json(res,429,{error:'Daily API request limit reached.',limit,used:used-1}); return null; }
  await sql`UPDATE customer_api_keys SET last_used_at=now() WHERE id=${key.id}`;
  return {userId:key.user_id,keyId:key.id,used,limit};
}
export async function runModel(req,res,skill) {
  const access=await authenticateApiKey(req,res); if(!access) return;
  const body=req.body||{}, prompt=String(body.prompt||'').trim();
  if(!prompt) return json(res,400,{error:'prompt is required.'});
  if(prompt.length>12000) return json(res,413,{error:'Prompt exceeds 12000 characters.'});
  const model=skill==='general'?'general-v0':'marketing-v0';
  const base=String(process.env.CAMPAIGN_STUDIO_MODEL_URL||'').replace(/\/$/,'');
  if(!base) return json(res,503,{error:'Your own model server is not connected yet. Train and deploy the Campaign Studio models, then set CAMPAIGN_STUDIO_MODEL_URL.'});
  const secret=process.env.MODEL_SERVER_SECRET;
  if(!secret) return json(res,503,{error:'Model server authentication is not configured.'});
  try {
    const upstream=await fetch(base+'/generate',{
      method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+secret},
      body:JSON.stringify({model,prompt,max_new_tokens:Math.min(400,Math.max(16,Number(body.max_new_tokens)||180))}),
      signal:AbortSignal.timeout(25000)
    });
    const data=await upstream.json().catch(()=>({}));
    if(!upstream.ok) return json(res,502,{error:'Campaign Studio model server returned an error.'});
    return json(res,200,{ok:true,skill,model,output:data.output||'',usage:{daily_requests_used:access.used,daily_request_limit:access.limit},notice:'Independent scratch-trained model output. Review before use.'});
  } catch(e) { console.error('private-model-request',e); return json(res,502,{error:'Could not reach your Campaign Studio model server.'}); }
}
