import type { CleaningServiceType } from '../types';

export const CLEANING_SERVICES: { value: CleaningServiceType; label: string }[] = [
  { value: 'residential_deep_cleaning', label: 'Residential deep cleaning' },
  { value: 'regular_house_cleaning', label: 'Regular house cleaning' },
  { value: 'post_construction_cleaning', label: 'Post-construction cleaning' },
  { value: 'office_cleaning', label: 'Office cleaning' },
  { value: 'commercial_facility_cleaning', label: 'Commercial facility cleaning' },
  { value: 'move_in_move_out_cleaning', label: 'Move-in or move-out cleaning' },
  { value: 'upholstery_cleaning', label: 'Upholstery cleaning' },
  { value: 'fumigation_pest_control', label: 'Fumigation or pest control' },
];

export function isCleaningServiceType(value: string): value is CleaningServiceType {
  return CLEANING_SERVICES.some((service) => service.value === value);
}
