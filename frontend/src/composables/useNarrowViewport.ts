import { onScopeDispose, ref } from 'vue'
export function useNarrowViewport() {
  const media = window.matchMedia('(max-width: 767px)')
  const narrow = ref(media.matches)
  const update = () => { narrow.value = media.matches }
  media.addEventListener('change', update)
  onScopeDispose(() => media.removeEventListener('change', update))
  return narrow
}
