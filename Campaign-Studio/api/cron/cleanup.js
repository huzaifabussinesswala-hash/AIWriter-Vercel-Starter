import {db,json} from '../_lib/core.js';
export default async function handler(req,res){
 if(req.method!=='GET'){res.setHeader('Allow','GET');return json(res,405,{error:'Method not allowed'})}
 const secret=process.env.CRON_SECRET;
 if(!secret||req.headers.authorization!=='Bearer '+secret)return json(res,401,{error:'Unauthorized'});
 try{const sql=db();const a=await sql`DELETE FROM email_otps WHERE expires_at<now()-interval '1 day' RETURNING id`;const b=await sql`DELETE FROM auth_sessions WHERE expires_at<now() RETURNING id`;const c=await sql`DELETE FROM auth_rate_limits WHERE window_started_at<now()-interval '2 days' RETURNING rate_key`;return json(res,200,{ok:true,deleted:{oldOtps:a.length,expiredSessions:b.length,oldRateLimits:c.length}})}
 catch(e){console.error('cleanup',e);return json(res,500,{error:'Cleanup failed.'})}
}