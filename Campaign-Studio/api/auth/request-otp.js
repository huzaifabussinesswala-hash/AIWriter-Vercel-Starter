import { db, json, method, emailAddress, hash, ipKey, rateLimit, createOtp } from '../_lib/core.js';
export default async function handler(req,res){
  if(!method(req,res,'POST')) return;
  try{
    const email=emailAddress(req.body?.email);
    if(!email) return json(res,400,{error:'Enter a valid email address.'});
    const secret=process.env.OTP_SECRET, apiKey=process.env.RESEND_API_KEY, from=process.env.EMAIL_FROM;
    if(!process.env.DATABASE_URL || !secret || secret.length<32 || !apiKey || !from)
      return json(res,503,{error:'Email verification is not configured yet.'});
    const sql=db(), ip=ipKey(req), emailKey=hash(email,secret);
    if(!await rateLimit(sql,'otp-ip:'+ip,12,900) || !await rateLimit(sql,'otp-email:'+emailKey,5,3600))
      return json(res,429,{error:'Too many code requests. Please try again later.'});
    const recent=await sql`SELECT id FROM email_otps WHERE email=${email} AND created_at>now()-interval '60 seconds' ORDER BY created_at DESC LIMIT 1`;
    if(recent.length) return json(res,429,{error:'Please wait 60 seconds before requesting another code.'});
    const code=createOtp();
    await sql`UPDATE email_otps SET consumed_at=now() WHERE email=${email} AND consumed_at IS NULL`;
    await sql`INSERT INTO email_otps(email,code_hash,expires_at) VALUES(${email},${hash(code,secret)},now()+interval '10 minutes')`;
    const sent=await fetch('https://api.resend.com/emails',{method:'POST',headers:{Authorization:'Bearer '+apiKey,'Content-Type':'application/json'},body:JSON.stringify({from,to:[email],subject:'Your Campaign Studio sign-in code',text:'Your Campaign Studio verification code is '+code+'. It expires in 10 minutes. If you did not request this, ignore this email.',html:'<div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;color:#202923"><p style="letter-spacing:3px;font-size:11px">CAMPAIGN STUDIO</p><h1 style="font-family:Georgia,serif;font-weight:normal">Your sign-in code</h1><p>Use this one-time code to access your private workspace.</p><p style="font-size:32px;letter-spacing:8px;font-weight:bold;background:#f4f2eb;padding:18px">'+code+'</p><p>This code expires in 10 minutes. If you did not request it, ignore this email.</p></div>'})});
    if(!sent.ok){await sql`UPDATE email_otps SET consumed_at=now() WHERE email=${email} AND consumed_at IS NULL`;return json(res,502,{error:'We could not send the email. Please try again shortly.'});}
    return json(res,200,{ok:true,message:'Verification code sent.'});
  }catch(e){console.error('request-otp',e);return json(res,500,{error:'Unable to start email verification right now.'});}
}