import { neon } from '@neondatabase/serverless';
import { createHash, createHmac, randomBytes, randomInt, timingSafeEqual } from 'node:crypto';

export function db() {
  if (!process.env.DATABASE_URL) throw new Error('DATABASE_URL is not configured');
  return neon(process.env.DATABASE_URL);
}
export function json(res, status, body) {
  res.status(status).setHeader('Content-Type','application/json; charset=utf-8').send(body);
}
export function method(req,res,expected) {
  if(req.method!==expected){res.setHeader('Allow',expected);json(res,405,{error:'Method not allowed'});return false;} return true;
}
export function emailAddress(value) {
  if(typeof value!=='string') return null;
  const e=value.trim().toLowerCase();
  return e.length<=254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e) ? e : null;
}
export function hash(value,secret) { return createHmac('sha256',secret).update(value).digest('hex'); }
export function sha(value) { return createHash('sha256').update(value).digest('hex'); }
export function safeEqual(a,b) {
  const x=Buffer.from(String(a)); const y=Buffer.from(String(b));
  return x.length===y.length && timingSafeEqual(x,y);
}
export function ipKey(req) {
  const raw=(req.headers['x-forwarded-for']||'unknown').toString().split(',')[0].trim();
  return sha(raw).slice(0,32);
}
export async function rateLimit(sql,key,limit,windowSeconds) {
  const rows=await sql`
    INSERT INTO auth_rate_limits (rate_key, window_started_at, attempts)
    VALUES (${key}, now(), 1)
    ON CONFLICT (rate_key) DO UPDATE SET
      window_started_at = CASE WHEN auth_rate_limits.window_started_at < now() - (${windowSeconds} * interval '1 second') THEN now() ELSE auth_rate_limits.window_started_at END,
      attempts = CASE WHEN auth_rate_limits.window_started_at < now() - (${windowSeconds} * interval '1 second') THEN 1 ELSE auth_rate_limits.attempts + 1 END
    RETURNING attempts
  `;
  return Number(rows[0]?.attempts||0)<=limit;
}
export function cookieOptions(maxAge) {
  return `campaign_session=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;
}
export async function requireUser(req,res,sql) {
  const raw=(req.headers.cookie||'').split(';').map(x=>x.trim()).find(x=>x.startsWith('campaign_session='))?.slice('campaign_session='.length);
  if(!raw) {json(res,401,{error:'Please verify your email to continue.'});return null;}
  const token=decodeURIComponent(raw);
  const rows=await sql`SELECT u.id,u.email FROM auth_sessions s JOIN campaign_users u ON u.id=s.user_id WHERE s.token_hash=${sha(token)} AND s.expires_at>now() LIMIT 1`;
  if(!rows.length){res.setHeader('Set-Cookie',cookieOptions(0));json(res,401,{error:'Your session has expired. Please sign in again.'});return null;}
  return rows[0];
}
export function createOtp(){return String(randomInt(0,1000000)).padStart(6,'0');}
export function createToken(){return randomBytes(32).toString('base64url');}
