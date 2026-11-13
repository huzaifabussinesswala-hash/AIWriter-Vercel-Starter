import { db, json, method, requireUser } from '../_lib/core.js';
export default async function handler(req,res){
  if(!method(req,res,'GET')) return;
  try{const user=await requireUser(req,res,db());if(!user)return;return json(res,200,{user:{email:user.email}});}
  catch(e){console.error('auth-me',e);return json(res,500,{error:'Unable to load your account.'});}
}