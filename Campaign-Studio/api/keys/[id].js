import {json} from '../_lib/core.js';
import {revokeApiKey} from '../_lib/customer-api.js';
export default async function handler(req,res){try{return await revokeApiKey(req,res);}catch(e){console.error('revoke-api-key',e);return json(res,500,{error:'Unable to revoke API key.'});}}
