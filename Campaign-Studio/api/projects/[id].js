import {db,json,requireUser} from '../_lib/core.js';
export default async function handler(req,res){
 if(req.method!=='DELETE'){res.setHeader('Allow','DELETE');return json(res,405,{error:'Method not allowed'})}
 try{const sql=db(),user=await requireUser(req,res,sql);if(!user)return;const id=Number(req.query?.id);if(!Number.isSafeInteger(id)||id<1)return json(res,400,{error:'Invalid project id.'});const rows=await sql`DELETE FROM campaign_projects WHERE id=${id} AND user_id=${user.id} RETURNING id`;if(!rows.length)return json(res,404,{error:'Project not found.'});return json(res,200,{ok:true})}
 catch(e){console.error('delete-project',e);return json(res,500,{error:'Unable to delete this project.'})}
}