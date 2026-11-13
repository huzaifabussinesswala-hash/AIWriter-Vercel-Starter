import {json,method} from '../_lib/core.js';
import {issueApiKey,listApiKeys} from '../_lib/customer-api.js';
export default async function handler(req,res){try{if(req.method==='POST')return await issueApiKey(req,res);if(req.method==='GET')return await listApiKeys(req,res);res.setHeader('Allow','GET, POST');return json(res,405,{error:'Method not allowed'});}catch(e){console.error('api-keys',e);return json(res,500,{error:'Unable to manage API keys.'});}}
