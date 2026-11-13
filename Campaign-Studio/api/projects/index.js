import { db, json, method, requireUser } from '../_lib/core.js';
export default async function handler(req,res){
  try{
    const sql=db(),user=await requireUser(req,res,sql);if(!user)return;
    if(req.method==='GET'){
      const rows=await sql`SELECT id,name,product_name,product_context,created_at FROM campaign_projects WHERE user_id=${user.id} ORDER BY created_at DESC LIMIT 50`;
      return json(res,200,{projects:rows});
    }
    if(req.method==='POST'){
      const name=String(req.body?.name||'').trim(),product=String(req.body?.product_name||'').trim(),context=String(req.body?.product_context||'').trim(),notes=String(req.body?.customer_notes||'').trim();
      if(!name||!product||!context) return json(res,400,{error:'Project name, product name and product context are required.'});
      if(name.length>100||product.length>140||context.length>5000||notes.length>12000) return json(res,400,{error:'One or more fields exceed the allowed length.'});
      const rows=await sql`INSERT INTO campaign_projects(user_id,name,product_name,product_context,customer_notes) VALUES(${user.id},${name},${product},${context},${notes}) RETURNING id,name,product_name,product_context,created_at`;
      return json(res,201,{project:rows[0]});
    }
    res.setHeader('Allow','GET, POST');return json(res,405,{error:'Method not allowed'});
  }catch(e){console.error('projects',e);return json(res,500,{error:'Unable to save or load projects.'});}
}