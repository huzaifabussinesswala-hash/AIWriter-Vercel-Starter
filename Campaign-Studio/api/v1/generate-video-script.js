import {json} from '../_lib/core.js';
import {runAI} from '../_lib/customer-api.js';
export default async function handler(req,res){if(req.method!=='POST'){res.setHeader('Allow','POST');return json(res,405,{error:'Method not allowed'});}try{return await runAI(req,res,'script');}catch(e){console.error('generate-video-script',e);return json(res,500,{error:'Unable to generate video script.'});}}
