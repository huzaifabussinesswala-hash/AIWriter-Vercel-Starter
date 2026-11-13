import {json} from '../_lib/core.js';
import {runAI} from '../_lib/customer-api.js';
export default async function handler(req,res){if(req.method!=='POST'){res.setHeader('Allow','POST');return json(res,405,{error:'Method not allowed'});}try{return await runAI(req,res,'analyze');}catch(e){console.error('analyze-feedback',e);return json(res,500,{error:'Unable to analyze feedback.'});}}
