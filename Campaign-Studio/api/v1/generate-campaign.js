import {json} from '../_lib/core.js';
import {runAI} from '../_lib/customer-api.js';
export default async function handler(req,res){if(req.method!=='POST'){res.setHeader('Allow','POST');return json(res,405,{error:'Method not allowed'});}try{return await runAI(req,res,'campaign');}catch(e){console.error('generate-campaign',e);return json(res,500,{error:'Unable to generate campaign.'});}}
