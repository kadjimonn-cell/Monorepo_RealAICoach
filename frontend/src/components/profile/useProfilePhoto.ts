// eslint-disable-next-line @typescript-eslint/no-unused-vars
import React, { useState, useCallback, useEffect, useRef } from 'react';
import { Alert, Platform } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import api from '../../services/api';

interface UseProfilePhotoOptions {
  initialImage: string | null;
  refreshUser: () => Promise<void>;
}

export function useProfilePhoto({ initialImage, refreshUser }: UseProfilePhotoOptions) {
  const [profileImage, setProfileImage] = useState<string | null>(initialImage);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  // Cropper state
  const [cropModalVisible, setCropModalVisible] = useState(false);
  const [rawImageSrc, setRawImageSrc] = useState<string | null>(null);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    setProfileImage(initialImage);
  }, [initialImage]);

  const drawPreview = useCallback(() => {
    if (!canvasRef.current || !imgRef.current || !rawImageSrc) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const img = imgRef.current;
    const size = 380;
    canvas.width = size;
    canvas.height = size;
    ctx.clearRect(0, 0, size, size);
    ctx.save();
    ctx.translate(size / 2, size / 2);
    ctx.rotate((rotation * Math.PI) / 180);
    ctx.scale(zoom, zoom);
    const scale = Math.max(size / img.naturalWidth, size / img.naturalHeight);
    const w = img.naturalWidth * scale;
    const h = img.naturalHeight * scale;
    ctx.translate(crop.x / zoom, crop.y / zoom);
    ctx.drawImage(img, -w / 2, -h / 2, w, h);
    ctx.restore();
    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.fillRect(0, 0, size, size);
    ctx.globalCompositeOperation = 'destination-out';
    ctx.beginPath();
    ctx.arc(size / 2, size / 2, size / 2 - 10, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
    ctx.strokeStyle = 'rgba(255,255,255,0.5)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(size / 2, size / 2, size / 2 - 10, 0, Math.PI * 2);
    ctx.stroke();
  }, [rawImageSrc, zoom, rotation, crop]);

  useEffect(() => {
    if (cropModalVisible && rawImageSrc) {
      const img = new window.Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => { imgRef.current = img; drawPreview(); };
      img.src = rawImageSrc;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cropModalVisible, rawImageSrc]);

  useEffect(() => { drawPreview(); }, [drawPreview]);

  const uploadPhotoFile = async (file: File) => {
    setUploading(true);
    setUploadProgress(0);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await api.post('/auth/upload-photo', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent: any) => {
          setUploadProgress(Math.round((progressEvent.loaded * 100) / (progressEvent.total || 1)));
        },
      });
      setProfileImage(response.data.profile_image_url);
      await refreshUser();
      Alert.alert('Success', 'Photo uploaded successfully!');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to upload photo');
    } finally {
      setUploading(false);
      setUploadProgress(0);
    }
  };

  const uploadPhotoUri = async (uri: string) => {
    setUploading(true);
    setUploadProgress(0);
    try {
      const formData = new FormData();
      formData.append('file', { uri, name: 'profile.jpg', type: 'image/jpeg' } as any);
      const response = await api.post('/auth/upload-photo', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent: any) => {
          setUploadProgress(Math.round((progressEvent.loaded * 100) / (progressEvent.total || 1)));
        },
      });
      setProfileImage(response.data.profile_image_url);
      await refreshUser();
      Alert.alert('Success', 'Photo uploaded successfully!');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to upload photo');
    } finally {
      setUploading(false);
      setUploadProgress(0);
    }
  };

  const pickImage = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/jpeg,image/png,image/webp';
      input.onchange = async (e: any) => {
        const file = e.target.files?.[0];
        if (!file) return;
        if (file.size > 10 * 1024 * 1024) { Alert.alert('Error', 'File too large. Maximum size is 10MB.'); return; }
        const reader = new FileReader();
        reader.onload = () => {
          setRawImageSrc(reader.result as string);
          setCrop({ x: 0, y: 0 });
          setZoom(1);
          setRotation(0);
          setCropModalVisible(true);
        };
        reader.readAsDataURL(file);
      };
      input.click();
      return;
    }
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') { Alert.alert('Permission Required', 'Please allow access to your photo library.'); return; }
    try {
      const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: true, aspect: [1, 1], quality: 0.7 });
      if (!result.canceled && result.assets[0]) await uploadPhotoUri(result.assets[0].uri);
    } catch { Alert.alert('Error', 'Failed to pick image.'); }
  };

  const takePhoto = async () => {
    if (Platform.OS === 'web') { pickImage(); return; }
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') { Alert.alert('Permission Required', 'Please allow camera access.'); return; }
    try {
      const result = await ImagePicker.launchCameraAsync({ allowsEditing: true, aspect: [1, 1], quality: 0.7 });
      if (!result.canceled && result.assets[0]) await uploadPhotoUri(result.assets[0].uri);
    } catch { Alert.alert('Error', 'Failed to take photo.'); }
  };

  const showImageOptions = () => {
    if (Platform.OS === 'web') { pickImage(); return; }
    Alert.alert('Profile Photo', 'Choose an option', [
      { text: 'Take Photo', onPress: takePhoto },
      { text: 'Choose from Library', onPress: pickImage },
      ...(profileImage ? [{ text: 'Remove Photo', onPress: removePhoto, style: 'destructive' as const }] : []),
      { text: 'Cancel', style: 'cancel' as const },
    ]);
  };

  const removePhoto = async () => {
    try { await api.delete('/auth/delete-photo'); setProfileImage(null); Alert.alert('Success', 'Profile photo removed.'); } catch { setProfileImage(null); }
  };

  const handleCropApply = async () => {
    if (!rawImageSrc || !canvasRef.current || !imgRef.current) return;
    setCropModalVisible(false);
    try {
      const img = imgRef.current;
      const outputSize = 400;
      const outputCanvas = document.createElement('canvas');
      outputCanvas.width = outputSize;
      outputCanvas.height = outputSize;
      const ctx = outputCanvas.getContext('2d')!;
      ctx.save();
      ctx.beginPath();
      ctx.arc(outputSize / 2, outputSize / 2, outputSize / 2, 0, Math.PI * 2);
      ctx.clip();
      ctx.translate(outputSize / 2, outputSize / 2);
      ctx.rotate((rotation * Math.PI) / 180);
      ctx.scale(zoom, zoom);
      const previewSize = 380;
      const scale = Math.max(previewSize / img.naturalWidth, previewSize / img.naturalHeight);
      const w = img.naturalWidth * scale;
      const h = img.naturalHeight * scale;
      ctx.translate(crop.x / zoom, crop.y / zoom);
      ctx.drawImage(img, -w / 2, -h / 2, w, h);
      ctx.restore();
      const blob = await new Promise<Blob>((resolve) => { outputCanvas.toBlob((b) => resolve(b!), 'image/png', 0.9); });
      const file = new File([blob], 'avatar.png', { type: 'image/png' });
      await uploadPhotoFile(file);
    } catch { Alert.alert('Error', 'Failed to crop image.'); } finally { setRawImageSrc(null); }
  };

  const handleCropCancel = () => { setCropModalVisible(false); setRawImageSrc(null); };

  return {
    profileImage, setProfileImage,
    uploading, uploadProgress,
    cropModalVisible, rawImageSrc,
    crop, setCrop, zoom, setZoom, rotation, setRotation,
    canvasRef, imgRef,
    showImageOptions, removePhoto,
    handleCropApply, handleCropCancel,
  };
}
