import { db, json, requireUser, sha } from './core.js';
import { randomBytes } from 'node:crypto';

export async function issueApiKey(req,res) {
  const sql=db(), user=await requireUser(req,res,sql); if(!user) return;
  const name=String(req.body?.name||'Default key').trim();
  if(!name||name.length>80) return json(res,400,{error:'Key name must be 1–80 characters.'});
  const raw='cst_live_'+randomBytes(32).toString('base64url');
  const prefix=raw.slice(0,20);
  const rows=await sql`INSERT INTO customer_api_keys(user_id,name,key_prefix,key_hash) VALUES(${user.id},${name},${prefix},${sha(raw)}) RETURNING id,name,key_prefix,created_at`;
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
  const token=auth.slice(7);
  const sql=db();
  const rows=await sql`SELECT id,user_id FROM customer_api_keys WHERE key_hash=${sha(token)} AND revoked_at IS NULL LIMIT 1`;
  if(!rows.length) { json(res,401,{error:'Invalid or revoked API key.'}); return null; }
  const key=rows[0];
  const usage=await sql`INSERT INTO api_usage_daily(user_id,usage_date,request_count) VALUES(${key.user_id},CURRENT_DATE,1)
    ON CONFLICT(user_id,usage_date) DO UPDATE SET request_count=api_usage_daily.request_count+1
    RETURNING request_count`;
  const used=Number(usage[0]?.request_count||0);
  const limit=Number(process.env.API_DAILY_REQUEST_LIMIT||100);
  if(used>limit) { json(res,429,{error:'Daily API request limit reached.',limit,used:used-1,retry:'Try again after the daily reset.'}); return null; }
  await sql`UPDATE customer_api_keys SET last_used_at=now() WHERE id=${key.id}`;
  return {userId:key.user_id,keyId:key.id,used,limit};
}
export async function runAI(req,res,task) {
  const access=await authenticateApiKey(req,res); if(!access) return;
  const body=req.body||{};
  const product=String(body.product_name||'').trim();
  const context=String(body.product_context||'').trim();
  const feedback=String(body.customer_feedback||'').trim();
  if(!product||!context||!feedback) return json(res,400,{error:'product_name, product_context and customer_feedback are required.'});
  if(product.length>140||context.length>4000||feedback.length>12000) return json(res,413,{error:'Input too large. Maximums: product 140, context 4000, feedback 12000 characters.'});
  if(!process.env.OPENAI_API_KEY) return json(res,503,{error:'AI service is not configured yet.'});
  const prompts={
    analyze:'Analyze customer feedback for a beauty product. Return concise JSON with keys: sentiment_summary, recurring_themes (array), customer_needs (array), objections (array), suggested_actions (array), claim_safety_flags (array). Distinguish customer opinions from verified product facts. Never invent product claims.',
    campaign:'Create a practical beauty marketing campaign grounded only in the supplied product context and customer feedback. Return JSON keys: campaign_angle, audience, hooks (array of 5), ad_copies (array of 3 with headline and body), objections_to_address (array), evidence_notes (array). Do not make medical or unsupported efficacy claims.',
    script:'Create a 20–30 second vertical short-form beauty video script. Return JSON keys: concept, duration_seconds, scenes (array of objects with seconds, visual, voiceover, on_screen_text), caption, claim_safety_flags. Avoid unsupported medical or efficacy claims.'
  };
  const input='Product: '+product+'\nProduct context (brand-supplied): '+context+'\nCustomer feedback (unverified opinions): '+feedback;
  try {
    const response=await fetch('https://api.openai.com/v1/chat/completions',{
      method:'POST',headers:{'Authorization':'Bearer '+process.env.OPENAI_API_KEY,'Content-Type':'application/json'},
      body:JSON.stringify({model:process.env.OPENAI_MODEL||'gpt-4o-mini',temperature:0.3,max_tokens:1100,response_format:{type:'json_object'},messages:[{role:'system',content:prompts[task]+' Output valid JSON only.'},{role:'user',content:input}]})
    });
    const data=await response.json();
    if(!response.ok){console.error('OpenAI API error',response.status,data?.error?.type);return json(res,502,{error:'AI provider request failed. Please try again later.'});}
    const raw=data.choices?.[0]?.message?.content||'{}';
    let result; try{result=JSON.parse(raw)}catch{return json(res,502,{error:'AI returned an unreadable response. Please retry.'});}
    return json(res,200,{ok:true,task,model:data.model,result,usage:{daily_requests_used:access.used,daily_request_limit:access.limit},disclaimer:'AI output is a draft. Review product facts and claims before publishing.'});
  } catch(e){console.error('AI request failed',e);return json(res,502,{error:'Unable to reach AI provider.'});}
}
