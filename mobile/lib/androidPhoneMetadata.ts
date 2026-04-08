import { NativeModules, PermissionsAndroid, Platform } from "react-native";

export interface AndroidPhoneMetadataStatus {
  ready: boolean;
  permissions?: {
    read_call_log?: string;
    read_sms?: string;
  };
  missing_permissions?: string[];
  status_label?: string;
}

export interface AndroidPhoneMetadataSource {
  [key: string]: unknown;
}

export interface AndroidPhoneMetadataItem {
  kind: string;
  record_id?: string;
  timestamp_ms: number;
  timestamp_iso?: string;
  title: string;
  summary: string;
  thread_id?: number;
  count?: number;
  unread_count?: number;
  source?: AndroidPhoneMetadataSource;
}

export interface AndroidPhoneMetadataSnapshot extends AndroidPhoneMetadataStatus {
  generated_at: string;
  call_log: AndroidPhoneMetadataItem[];
  sms_threads: AndroidPhoneMetadataItem[];
  review_queue: AndroidPhoneMetadataItem[];
  error?: string;
}

type NativePhoneMetadataModule = {
  getStatus: () => Promise<AndroidPhoneMetadataStatus>;
  getSnapshot: (options?: Record<string, unknown>) => Promise<AndroidPhoneMetadataSnapshot>;
};

const nativeModule = NativeModules.PhoneMetadata as NativePhoneMetadataModule | undefined;

function ensureAndroidSupport(): void {
  if (Platform.OS !== "android") {
    throw new Error("Android phone metadata is only available on Android devices.");
  }
  if (!nativeModule) {
    throw new Error("Android phone metadata native module is unavailable.");
  }
}

export async function requestPhoneMetadataPermissions(): Promise<AndroidPhoneMetadataStatus> {
  ensureAndroidSupport();

  const permissions = [
    PermissionsAndroid.PERMISSIONS.READ_CALL_LOG,
    PermissionsAndroid.PERMISSIONS.READ_SMS,
  ];

  await PermissionsAndroid.requestMultiple(permissions);
  return nativeModule!.getStatus();
}

export async function loadPhoneMetadataStatus(): Promise<AndroidPhoneMetadataStatus> {
  ensureAndroidSupport();
  return nativeModule!.getStatus();
}

export async function loadPhoneMetadataSnapshot(options?: {
  limitCalls?: number;
  limitSms?: number;
}): Promise<AndroidPhoneMetadataSnapshot> {
  ensureAndroidSupport();
  return nativeModule!.getSnapshot({
    limitCalls: options?.limitCalls ?? 8,
    limitSms: options?.limitSms ?? 8,
  });
}
