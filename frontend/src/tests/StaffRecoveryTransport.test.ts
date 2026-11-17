import { afterEach, expect, it } from 'vitest';
import { AxiosError, type AxiosAdapter } from 'axios';
import { api } from '@/services/api';
import { staffService } from '@/services/staffService';
import { useAuthStore } from '@/stores/authStore';

const original=api.defaults.adapter;
afterEach(()=>{api.defaults.adapter=original;});
it('actual anonymous recovery service sends only JSON proof and never attaches or replaces the current session',async()=>{
  useAuthStore.setState({accessToken:'unrelated-owner-session',user:null});
  let called=0;
  api.defaults.adapter=(async config=>{
    called++;expect(config.url).toBe('/auth/staff/recover-credential');
    expect(config.headers.get('Authorization')).toBe('');expect(config.skipAuthInterceptors).toBe(true);
    expect(JSON.parse(config.data)).toEqual({recovery_token:'synthetic-proof',new_password:'SyntheticPassword!9'});
    return {data:{success:true,data:{action:'password_recovered',login_required:true}},status:200,statusText:'OK',headers:{},config};
  }) as AxiosAdapter;
  await staffService.recover('synthetic-proof','SyntheticPassword!9');expect(called).toBe(1);
  expect(useAuthStore.getState().accessToken).toBe('unrelated-owner-session');
});
it('anonymous 401 is not retried with an unrelated refresh token or global logout',async()=>{
  useAuthStore.setState({accessToken:'unrelated-owner-session',user:null});let calls=0;
  api.defaults.adapter=(async config=>{calls++;throw new AxiosError('synthetic refusal','ERR_BAD_REQUEST',config,undefined,{data:{code:'INVALID_OR_EXPIRED_STAFF_RECOVERY_TOKEN'},status:401,statusText:'Unauthorized',headers:{},config});}) as AxiosAdapter;
  await expect(staffService.recover('synthetic-proof','SyntheticPassword!9')).rejects.toBeInstanceOf(AxiosError);
  expect(calls).toBe(1);expect(useAuthStore.getState().accessToken).toBe('unrelated-owner-session');
});
