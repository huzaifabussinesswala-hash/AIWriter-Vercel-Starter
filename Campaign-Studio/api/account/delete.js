import {db,json,requireUser} from '../_lib/core.js';
export default async function handler(req,res){
 if(req.method!=='DELETE'){res.setHeader('Allow','DELETE');return json(res,405,{error:'Method not allowed'})}
 try{const sql=db(),user=await requireUser(req,res,sql);if(!user)return;await sql`DELETE FROM email_otps WHERE email=${user.email}`;await sql`DELETE FROM campaign_users WHERE id=${user.id}`;res.setHeader('Set-Cookie','campaign_session=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0');return json(res,200,{ok:true})}
 catch(e){console.error('delete-account',e);return json(res,500,{error:'Unable to delete your account right now.'})}
}