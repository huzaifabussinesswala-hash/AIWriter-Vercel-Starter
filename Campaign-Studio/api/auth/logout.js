import { db, json, method, sha, cookieOptions } from '../_lib/core.js';
export default async function handler(req,res){
  if(!method(req,res,'POST')) return;
  try{
    const raw=(req.headers.cookie||'').split(';').map(x=>x.trim()).find(x=>x.startsWith('campaign_session='))?.slice('campaign_session='.length);
    if(raw){const sql=db();await sql`DELETE FROM auth_sessions WHERE token_hash=${sha(decodeURIComponent(raw))}`;}
    res.setHeader('Set-Cookie',cookieOptions(0));return json(res,200,{ok:true});
  }catch(e){console.error('logout',e);res.setHeader('Set-Cookie',cookieOptions(0));return json(res,200,{ok:true});}
}