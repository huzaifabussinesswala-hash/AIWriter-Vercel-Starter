import {json} from '../_lib/core.js';
import {runModel} from '../_lib/customer-api.js';
export default async function handler(req,res){if(req.method!=='POST'){res.setHeader('Allow','POST');return json(res,405,{error:'Method not allowed'});}try{return await runModel(req,res,'marketing');}catch(e){console.error('marketing-model',e);return json(res,500,{error:'Model request failed.'});}}
