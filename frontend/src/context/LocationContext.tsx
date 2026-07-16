import React, { createContext, useContext, useEffect, useState } from 'react';
import * as Location from 'expo-location';
import { Platform } from 'react-native';
import { clientLogger } from '../utils/clientLogger';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

interface LocationContextType {
  location: Location.LocationObject | null;
  address: Location.LocationGeocodedAddress | null;
  errorMsg: string | null;
  timezone: string;
  detectedLocale: string;
  refreshLocation: () => Promise<void>;
}

const LocationContext = createContext<LocationContextType>({
  location: null,
  address: null,
  errorMsg: null,
  timezone: 'UTC',
  detectedLocale: 'en',
  refreshLocation: async () => {},
});

export function LocationProvider({ children }: { children: React.ReactNode }) {
  const [location, setLocation] = useState<Location.LocationObject | null>(null);
  const [address, setAddress] = useState<Location.LocationGeocodedAddress | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [timezone, setTimezone] = useState<string>(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC');
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [detectedLocale, setDetectedLocale] = useState<string>(Platform.OS === 'web' && typeof navigator !== 'undefined' ? (navigator?.language?.split('-')[0] || 'en') : 'en');

  const refreshLocation = async () => {
    try {
      let { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        setErrorMsg('Permission to access location was denied');
        return;
      }

      let loc = await Location.getCurrentPositionAsync({});
      setLocation(loc);

      // Detect timezone from coordinates
      try {
        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        if (tz) setTimezone(tz);
      } catch (error) { handleAppRecoverableError({ scope: 'src/context/LocationContext.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }

      // Reverse Geocode
      try {
        let addresses = await Location.reverseGeocodeAsync(loc.coords);
        if (addresses && addresses.length > 0) {
          setAddress(addresses[0]);
        }
      } catch (e) {
        clientLogger.log('Geocoding failed', e);
      }
    } catch {
      setErrorMsg('Failed to get location');
    }
  };

  useEffect(() => {
    try {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (tz) setTimezone(tz);
    } catch (error) { handleAppRecoverableError({ scope: 'src/context/LocationContext.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  return (
    <LocationContext.Provider value={{ location, address, errorMsg, timezone, detectedLocale, refreshLocation }}>
      {children}
    </LocationContext.Provider>
  );
}

export const useLocation = () => useContext(LocationContext);
