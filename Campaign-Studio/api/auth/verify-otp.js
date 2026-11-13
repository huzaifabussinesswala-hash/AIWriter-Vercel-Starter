import { db, json, method, emailAddress, hash, ipKey, rateLimit, safeEqual, createToken, sha } from '../_lib/core.js';
export default async function handler(req,res){
  if(!method(req,res,'POST')) return;
  try{
    const email=emailAddress(req.body?.email), code=String(req.body?.code||'').trim();
    if(!email || !/^\d{6}$/.test(code)) return json(res,400,{error:'Enter the email address and 6-digit code.'});
    const secret=process.env.OTP_SECRET;
    if(!process.env.DATABASE_URL || !secret || secret.length<32) return json(res,503,{error:'Email verification is not configured yet.'});
    const sql=db();
    if(!await rateLimit(sql,'verify-ip:'+ipKey(req),20,900) || !await rateLimit(sql,'verify-email:'+hash(email,secret),8,900))
      return json(res,429,{error:'Too many verification attempts. Try again later.'});
    const rows=await sql`SELECT id,code_hash FROM email_otps WHERE email=${email} AND consumed_at IS NULL AND expires_at>now() ORDER BY created_at DESC LIMIT 1`;
    if(!rows.length || !safeEqual(rows[0].code_hash,hash(code,secret))) return json(res,400,{error:'That code is invalid or expired. Request a new one.'});
    const consumed=await sql`UPDATE email_otps SET consumed_at=now() WHERE id=${rows[0].id} AND consumed_at IS NULL RETURNING id`;
    if(!consumed.length) return json(res,400,{error:'That code has already been used. Request a new one.'});
    const users=await sql`INSERT INTO campaign_users(email) VALUES(${email}) ON CONFLICT(email) DO UPDATE SET last_seen_at=now() RETURNING id,email`;
    const token=createToken(), expires=new Date(Date.now()+7*24*60*60*1000);
    await sql`INSERT INTO auth_sessions(user_id,token_hash,expires_at) VALUES(${users[0].id},${sha(token)},${expires.toISOString()})`;
    res.setHeader('Set-Cookie',`campaign_session=${encodeURIComponent(token)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=604800`);
    return json(res,200,{ok:true,user:{email:users[0].email}});
  }catch(e){console.error('verify-otp',e);return json(res,500,{error:'Unable to verify this code right now.'});}
}