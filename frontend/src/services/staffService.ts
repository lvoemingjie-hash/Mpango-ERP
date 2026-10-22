import { api } from './api';
import type { StaffMember, StaffTemplate, StaffTemplateKey } from '@/types/staff';

export const staffService = {
  list: async () => (await api.get<{data:{items:StaffMember[];owner_id:string;authz_revision:number}}>('/staff')).data.data,
  templates: async () => (await api.get<{data:StaffTemplate[]}>('/staff/role-templates')).data.data,
  create: async (body:{email:string;full_name:string;template_key:StaffTemplateKey;adopt_existing:boolean},key:string) =>
    (await api.post<{data:StaffMember}>('/staff',body,{headers:{'Idempotency-Key':key}})).data.data,
  edit: async (member:StaffMember,body:{is_active?:boolean;template_key?:StaffTemplateKey}) =>
    (await api.patch<{data:StaffMember}>(`/staff/${member.id}`,{...body,expected_version:member.version})).data.data,
  invite: async (member:StaffMember,password:string) =>
    (await api.post(`/staff/${member.id}/credential-setup`,{expected_version:member.version,owner_password:password})).data,
  editTemplate: async (template:StaffTemplate,codes:string[]) =>
    (await api.put('/staff/role-templates/'+template.key,{expected_version:template.version,permission_codes:codes})).data,
  consume: async (token:string,password:string) =>
    (await api.post('/auth/staff/setup-credential',{setup_token:token,password},
      {headers:{Authorization:''},skipAuthInterceptors:true})).data,
};
