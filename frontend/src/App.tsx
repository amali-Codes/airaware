import { useState } from 'react'

const API_URL = 'http://127.0.0.1:8000'

export type Lifestyle =
  | 'student'
  | 'working professional'
  | 'homemaker'
  | 'retired'
  | 'other'

export type HouseholdMember =
  | 'adults'
  | 'children'
  | 'elderly people'
  | 'infants'

export type Sensitivity =
  | 'asthma'
  | 'allergies'
  | 'respiratory sensitivity'
  | 'none'

export type ExerciseHabits = 'indoor' | 'outdoor' | 'both'

export interface UserProfile {
  lifestyle: Lifestyle
  household_members: HouseholdMember[]
  sensitivity_considerations: Sensitivity
  exercise_habits: ExerciseHabits
  has_air_purifier: boolean
  uses_mask_outdoors: boolean
}

const defaultProfile: UserProfile = {
  lifestyle: 'other',
  household_members: ['adults'],
  sensitivity_considerations: 'none',
  exercise_habits: 'both',
  has_air_purifier: false,
  uses_mask_outdoors: false,
}

interface AirQualityResponse {
  location: {
    name: string
    latitude: number
    longitude: number
    country?: string | null
    timezone?: string | null
  }
  current: {
    timestamp: string
    us_aqi: {
      value: number | null
      category: string
      description: string
      color: string
    }
    european_aqi: number | null
    pollutants: {
      pm2_5: number | null
      pm10: number | null
      nitrogen_dioxide: number | null
      ozone: number | null
      sulphur_dioxide: number | null
      carbon_monoxide: number | null
    }
    units: Record<string, string>
  }
  summary: string
}

interface AIRecommendations {
  outdoor_activity: string
  sensitive_groups: string
  protection_tips: string[]
  summary: string
  source: 'gemini' | 'fallback'
}

function App() {
  const [location, setLocation] = useState('Bengaluru')
  const [data, setData] = useState<AirQualityResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [recommendations, setRecommendations] =
    useState<AIRecommendations | null>(null)
  const [recommendationsLoading, setRecommendationsLoading] = useState(false)
  const [recommendationsError, setRecommendationsError] = useState('')

  // Personalization profile state
  const [userProfile, setUserProfile] = useState<UserProfile>(defaultProfile)
  const [isProfileExpanded, setIsProfileExpanded] = useState(false)

  // Fetch only recommendations using POST /api/recommendations
  const fetchRecommendations = async (
    targetCity: string,
    profile: UserProfile
  ) => {
    setRecommendationsLoading(true)
    setRecommendationsError('')

    try {
      const response = await fetch(`${API_URL}/api/recommendations`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          city: targetCity,
          profile: profile,
        }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(
          errorData.detail || 'Unable to generate recommendations.'
        )
      }

      const recResult: AIRecommendations = await response.json()
      setRecommendations(recResult)
    } catch (err) {
      setRecommendations(null)
      setRecommendationsError(
        err instanceof Error
          ? err.message
          : 'Failed to load recommendations.'
      )
    } finally {
      setRecommendationsLoading(false)
    }
  }

  // Search city: fetches live AQI + recommendations
  const searchCity = async () => {
    const city = location.trim()

    if (!city) {
      setError('Please enter a city name.')
      return
    }

    setLoading(true)
    setError('')
    setData(null)
    setRecommendations(null)
    setRecommendationsError('')

    try {
      // 1. Fetch air quality data via GET /api/air-quality
      const response = await fetch(
        `${API_URL}/api/air-quality?city=${encodeURIComponent(city)}`
      )

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(
          errorData.detail || 'Unable to retrieve air quality data.'
        )
      }

      const result: AirQualityResponse = await response.json()
      setData(result)

      // 2. Fetch personalized recommendations via POST /api/recommendations
      await fetchRecommendations(result.location.name || city, userProfile)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Something went wrong. Please try again.'
      )
    } finally {
      setLoading(false)
    }
  }

  // Refresh only recommendations without re-fetching AQI
  const updateRecommendations = async () => {
    const city = data?.location.name || location.trim()
    if (!city) {
      setError('Please search for a city first.')
      return
    }
    await fetchRecommendations(city, userProfile)
  }

  // Immutable household members toggle
  const toggleHouseholdMember = (member: HouseholdMember) => {
    setUserProfile((prev) => {
      const exists = prev.household_members.includes(member)
      return {
        ...prev,
        household_members: exists
          ? prev.household_members.filter((m) => m !== member)
          : [...prev.household_members, member],
      }
    })
  }

  const pollutants = [
    {
      name: 'PM2.5',
      description: 'Fine particles',
      value: data?.current.pollutants.pm2_5,
      unit: 'pm2_5',
    },
    {
      name: 'PM10',
      description: 'Coarse particles',
      value: data?.current.pollutants.pm10,
      unit: 'pm10',
    },
    {
      name: 'NO₂',
      description: 'Nitrogen dioxide',
      value: data?.current.pollutants.nitrogen_dioxide,
      unit: 'nitrogen_dioxide',
    },
    {
      name: 'O₃',
      description: 'Ozone',
      value: data?.current.pollutants.ozone,
      unit: 'ozone',
    },
    {
      name: 'SO₂',
      description: 'Sulphur dioxide',
      value: data?.current.pollutants.sulphur_dioxide,
      unit: 'sulphur_dioxide',
    },
    {
      name: 'CO',
      description: 'Carbon monoxide',
      value: data?.current.pollutants.carbon_monoxide,
      unit: 'carbon_monoxide',
    },
  ]

  const formatValue = (value: number | null | undefined) => {
    return value == null ? '--' : Number(value.toFixed(2)).toString()
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <nav className="flex items-center justify-between border-b border-slate-800 px-8 py-5">
        <h1 className="text-2xl font-bold tracking-tight">
          <span className="text-emerald-400">Air</span>Aware
        </h1>
        <span className="text-sm text-slate-400">
          Your personal air quality assistant
        </span>
      </nav>

      <main className="mx-auto max-w-7xl px-6 py-10">
        <section className="mb-10">
          <p className="mb-3 text-sm font-medium uppercase tracking-widest text-emerald-400">
            Breathe smarter. Live healthier.
          </p>

          <h2 className="text-4xl font-bold md:text-5xl">
            Understand the air <br /> around you.
          </h2>

          <p className="mt-4 max-w-xl text-slate-400">
            Get air quality insights and personalised recommendations
            to protect your everyday health.
          </p>
        </section>

        {/* City search */}
        <section className="mb-8 flex max-w-xl gap-3">
          <input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') searchCity()
            }}
            placeholder="Enter your city..."
            className="w-full rounded-xl border border-slate-700 bg-slate-900 px-5 py-3 outline-none focus:border-emerald-400"
          />

          <button
            onClick={searchCity}
            disabled={loading}
            className="rounded-xl bg-emerald-400 px-6 py-3 font-semibold text-slate-950 hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? 'Loading...' : 'Search'}
          </button>
        </section>

        {/* Error message */}
        {error && (
          <div className="mb-6 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* Air quality overview */}
        <section className="grid gap-6 md:grid-cols-3">
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 md:col-span-2">
            <p className="text-sm text-slate-400">
              Air quality overview
            </p>

            <h3 className="mt-2 text-2xl font-semibold">
              {data
                ? `${data.location.name}${data.location.country ? `, ${data.location.country}` : ''}`
                : location}
            </h3>

            <p className="mt-1 text-xs text-slate-500">
              {data
                ? 'Source: Open-Meteo · Model-based air quality estimate · US AQI'
                : 'Search a city to retrieve air quality data.'}
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-8">
              <div>
                <p
                  className="text-7xl font-bold"
                  style={{
                    color: data?.current.us_aqi.color || '#10b981',
                  }}
                >
                  {data?.current.us_aqi.value ?? '--'}
                </p>

                <p className="mt-2 text-sm text-slate-400">
                  US AQI
                </p>
              </div>

              <div className="max-w-md">
                <p className="text-xl font-semibold">
                  {loading
                    ? 'Fetching air quality...'
                    : data?.current.us_aqi.category || 'Awaiting data'}
                </p>

                <p className="mt-2 text-sm leading-6 text-slate-400">
                  {data
                    ? data.current.us_aqi.description
                    : 'Search for a city to see its current air quality information.'}
                </p>
              </div>
            </div>

            {data && (
              <div className="mt-8 border-t border-slate-800 pt-4 text-xs text-slate-500">
                European AQI: {data.current.european_aqi ?? '--'}
                <br />
                Updated: {data.current.timestamp}
              </div>
            )}
          </div>

          {/* Daily insight */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <p className="text-sm text-slate-400">
              Your daily insight
            </p>

            <div className="mt-6 text-4xl">🌿</div>

            <h3 className="mt-4 text-xl font-semibold">
              {data?.current.us_aqi.category || 'Breathe better'}
            </h3>

            <p className="mt-2 text-sm leading-6 text-slate-400">
              {data
                ? data.summary
                : 'Air quality information and personalised guidance will appear here after your city search.'}
            </p>
          </div>
        </section>

        {/* Pollutant monitoring */}
        <section className="mt-8">
          <h3 className="mb-4 text-xl font-semibold">
            Pollutant monitoring
          </h3>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {pollutants.map((pollutant) => (
              <div
                key={pollutant.name}
                className="rounded-2xl border border-slate-800 bg-slate-900 p-5"
              >
                <p className="text-lg font-semibold">
                  {pollutant.name}
                </p>

                <p className="mt-2 text-sm text-slate-400">
                  {pollutant.description}
                </p>

                <p className="mt-5 text-2xl font-bold text-emerald-400">
                  {formatValue(pollutant.value)}
                </p>

                <p className="text-xs text-slate-500">
                  {pollutant.value == null
                    ? 'No reading available'
                    : data?.current.units[pollutant.unit] || 'Unit unavailable'}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* Expandable Personalize Your Guidance Section */}
        <section className="mt-10 rounded-2xl border border-slate-800 bg-slate-900 p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xl">⚙️</span>
                <h3 className="text-xl font-bold">Personalize Your Guidance</h3>
              </div>
              <p className="mt-1 text-sm text-slate-400">
                Tailor recommendations to your daily routine, household, and sensitivities.
              </p>
            </div>

            <button
              type="button"
              onClick={() => setIsProfileExpanded(!isProfileExpanded)}
              className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-800/80 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:border-emerald-500/50 hover:bg-slate-800"
            >
              <span>{isProfileExpanded ? 'Collapse' : 'Customize profile'}</span>
              <span className="text-xs text-slate-400">
                {isProfileExpanded ? '▲' : '▼'}
              </span>
            </button>
          </div>

          {/* Collapsed summary badges */}
          {!isProfileExpanded && (
            <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <span className="rounded-lg bg-slate-800 px-3 py-1 text-slate-300 capitalize">
                Lifestyle: {userProfile.lifestyle}
              </span>
              <span className="rounded-lg bg-slate-800 px-3 py-1 text-slate-300">
                Household:{' '}
                {userProfile.household_members.length > 0
                  ? userProfile.household_members.join(', ')
                  : 'None specified'}
              </span>
              {userProfile.sensitivity_considerations !== 'none' && (
                <span className="rounded-lg bg-amber-500/10 px-3 py-1 text-amber-300 capitalize">
                  Sensitivity: {userProfile.sensitivity_considerations}
                </span>
              )}
              <span className="rounded-lg bg-slate-800 px-3 py-1 text-slate-300 capitalize">
                Exercise: {userProfile.exercise_habits}
              </span>
              {userProfile.has_air_purifier && (
                <span className="rounded-lg bg-emerald-500/10 px-3 py-1 text-emerald-300">
                  Air purifier: Yes
                </span>
              )}
              {userProfile.uses_mask_outdoors && (
                <span className="rounded-lg bg-emerald-500/10 px-3 py-1 text-emerald-300">
                  Mask outdoors: Yes
                </span>
              )}
            </div>
          )}

          {/* Expanded form controls */}
          {isProfileExpanded && (
            <div className="mt-6 border-t border-slate-800 pt-6">
              <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {/* Lifestyle Dropdown */}
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Lifestyle / Routine
                  </label>
                  <select
                    value={userProfile.lifestyle}
                    onChange={(e) =>
                      setUserProfile({
                        ...userProfile,
                        lifestyle: e.target.value as Lifestyle,
                      })
                    }
                    className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-slate-200 outline-none focus:border-emerald-400"
                  >
                    <option value="other">Other / General</option>
                    <option value="student">Student</option>
                    <option value="working professional">Working professional</option>
                    <option value="homemaker">Homemaker</option>
                    <option value="retired">Retired</option>
                  </select>
                </div>

                {/* Health Sensitivities Dropdown */}
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Health Sensitivities
                  </label>
                  <select
                    value={userProfile.sensitivity_considerations}
                    onChange={(e) =>
                      setUserProfile({
                        ...userProfile,
                        sensitivity_considerations: e.target.value as Sensitivity,
                      })
                    }
                    className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-slate-200 outline-none focus:border-emerald-400"
                  >
                    <option value="none">None</option>
                    <option value="asthma">Asthma</option>
                    <option value="allergies">Allergies</option>
                    <option value="respiratory sensitivity">
                      Respiratory sensitivity
                    </option>
                  </select>
                </div>

                {/* Exercise Habits Dropdown */}
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Exercise Habits
                  </label>
                  <select
                    value={userProfile.exercise_habits}
                    onChange={(e) =>
                      setUserProfile({
                        ...userProfile,
                        exercise_habits: e.target.value as ExerciseHabits,
                      })
                    }
                    className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-slate-200 outline-none focus:border-emerald-400"
                  >
                    <option value="both">Both indoor & outdoor</option>
                    <option value="outdoor">Outdoor workouts</option>
                    <option value="indoor">Indoor workouts</option>
                  </select>
                </div>

                {/* Household Members Checkboxes */}
                <div className="sm:col-span-2 lg:col-span-3">
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Household Members (select all that apply)
                  </label>
                  <div className="mt-2.5 flex flex-wrap gap-2.5">
                    {(
                      [
                        ['adults', 'Adults'],
                        ['children', 'Children'],
                        ['elderly people', 'Elderly people'],
                        ['infants', 'Infants'],
                      ] as const
                    ).map(([value, label]) => {
                      const isSelected =
                        userProfile.household_members.includes(value)
                      return (
                        <button
                          type="button"
                          key={value}
                          onClick={() => toggleHouseholdMember(value)}
                          className={`rounded-xl border px-4 py-2 text-xs font-medium transition-colors ${isSelected
                              ? 'border-emerald-500/60 bg-emerald-500/10 text-emerald-300'
                              : 'border-slate-800 bg-slate-950 text-slate-400 hover:border-slate-700'
                            }`}
                        >
                          {isSelected ? '✓ ' : '+ '}
                          {label}
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Air Purifier Toggle */}
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    id="purifier-toggle"
                    checked={userProfile.has_air_purifier}
                    onChange={(e) =>
                      setUserProfile({
                        ...userProfile,
                        has_air_purifier: e.target.checked,
                      })
                    }
                    className="h-4 w-4 rounded border-slate-700 bg-slate-950 text-emerald-500 focus:ring-emerald-400"
                  />
                  <label
                    htmlFor="purifier-toggle"
                    className="cursor-pointer text-sm text-slate-300"
                  >
                    I have an indoor air purifier
                  </label>
                </div>

                {/* Mask Usage Toggle */}
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    id="mask-toggle"
                    checked={userProfile.uses_mask_outdoors}
                    onChange={(e) =>
                      setUserProfile({
                        ...userProfile,
                        uses_mask_outdoors: e.target.checked,
                      })
                    }
                    className="h-4 w-4 rounded border-slate-700 bg-slate-950 text-emerald-500 focus:ring-emerald-400"
                  />
                  <label
                    htmlFor="mask-toggle"
                    className="cursor-pointer text-sm text-slate-300"
                  >
                    I wear a mask outdoors
                  </label>
                </div>
              </div>

              {/* Update recommendations button */}
              <div className="mt-6 flex justify-end border-t border-slate-800/80 pt-4">
                <button
                  type="button"
                  onClick={updateRecommendations}
                  disabled={recommendationsLoading || !data}
                  className="rounded-xl bg-emerald-400 px-5 py-2.5 text-sm font-semibold text-slate-950 transition-colors hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {recommendationsLoading
                    ? 'Updating recommendations...'
                    : 'Update recommendations'}
                </button>
              </div>
            </div>
          )}
        </section>

        {/* AI Health Recommendations */}
        <section className="mt-10">
          <div className="mb-5">
            <p className="text-sm font-medium uppercase tracking-widest text-emerald-400">
              AirAware intelligence
            </p>
            <h3 className="mt-2 text-2xl font-bold">
              AI Health Recommendations
            </h3>
            <p className="mt-2 text-sm text-slate-400">
              Personalized guidance based on your profile and city's air quality.
            </p>
          </div>

          {recommendationsLoading && (
            <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 text-slate-400">
              Generating your health recommendations...
            </div>
          )}

          {recommendationsError && (
            <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-5 text-sm text-amber-300">
              {recommendationsError}
            </div>
          )}

          {!recommendationsLoading && recommendations && (
            <div className="grid gap-5 md:grid-cols-2">
              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
                <h4 className="text-lg font-semibold text-emerald-400">
                  🌿 Outdoor activities
                </h4>
                <p className="mt-3 text-sm leading-7 text-slate-300">
                  {recommendations.outdoor_activity}
                </p>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
                <h4 className="text-lg font-semibold text-emerald-400">
                  🫁 Sensitive groups
                </h4>
                <p className="mt-3 text-sm leading-7 text-slate-300">
                  {recommendations.sensitive_groups}
                </p>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
                <h4 className="text-lg font-semibold text-emerald-400">
                  🛡️ Protection tips
                </h4>
                <ul className="mt-3 space-y-3 text-sm leading-6 text-slate-300">
                  {recommendations.protection_tips.map((tip, index) => (
                    <li key={index} className="flex gap-3">
                      <span className="text-emerald-400">✓</span>
                      <span>{tip}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
                <h4 className="text-lg font-semibold text-emerald-400">
                  💡 AI summary
                </h4>
                <p className="mt-3 text-sm leading-7 text-slate-300">
                  {recommendations.summary}
                </p>
                <p className="mt-5 text-xs text-slate-500">
                  Generated by:{' '}
                  {recommendations.source === 'gemini'
                    ? 'Gemini AI'
                    : 'Rule-based fallback'}
                </p>
              </div>
            </div>
          )}
        </section>

        <footer className="mt-16 border-t border-slate-800 py-6 text-center text-sm text-slate-500">
          AirAware · Making every breath count.
        </footer>
      </main>
    </div>
  )
}

export default App
