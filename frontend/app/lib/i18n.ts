import type { LanguageCode } from "./LanguageContext";

type Messages = {
  navbar: {
    cropScanner: string;
    irrigation: string;
    yield: string;
    urban: string;
    signIn: string;
    getStarted: string;
    createAccount: string;
    logout: string;
  };
  scan: {
    title: string;
    analyzeBtn: string;
    actionPlanTitle: string;
    healthStatus: string;
    identifiedCondition: string;
    visibleSymptoms: string;
    organicRemedies: string;
    chemicalRemedies: string;
    preventiveMeasures: string;
    uploader: {
      dropLabel: string;
      dragLabel: string;
      browseLabel: string;
      acceptedLabel: string;
      removeChange: string;
    };
  };
  irrigation: {
    title: string;
    cropType: string;
    growthStage: string;
    soilType: string;
    fieldSize: string;
    soilMoisture: (v: number) => string;
    temperature: string;
    rainfallProbability: string;
    analyzeBtn: string;
    totalWaterRequired: string;
    evapotranspirationIndex: string;
    recommendedSchedule: string;
    weatherContext: string;
    tipsHeader: string;
  };
  yield: {
    title: string;
    cropType: string;
    fieldSize: string;
    historicalYield: string;
    soilType: string;
    irrigationType: string;
    weatherCondition: string;
    predictBtn: string;
    loadingPredict: string;
    estimatedYield: string;
    keyDrivers: string;
    optimizationSuggestions: string;
  };
  urban: {
    title: string;
    plantType: string;
    spaceType: string;
    dailySunlight: (v: number) => string;
    containerSize: string;
    submitBtn: string;
    loading: string;
    infoCareSchedule: string;
    infoWateringFrequency: string;
    infoSunlightRecommendations: string;
    infoSoilMix: string;
    actionableTips: string;
  };
};

type MessagesWithNav = Messages & {
  nav: Messages["navbar"];
};

const en: Messages = {
  navbar: {
    cropScanner: "Crop Scanner",
    irrigation: "Smart Irrigation",
    yield: "Yield Optimizer",
    urban: "Urban Gardening",
    signIn: "Sign In",
    getStarted: "Get Started",
    createAccount: "Create Account",
    logout: "Logout",
  },
  scan: {
    title: "Crop Disease Scanner",
    analyzeBtn: "Analyze Crop Health",
    actionPlanTitle: "Action Plan & Remedies",
    healthStatus: "Health Status",
    identifiedCondition: "Identified Condition",
    visibleSymptoms: "Visible Symptoms",
    organicRemedies: "Organic Remedies",
    chemicalRemedies: "Chemical Remedies",
    preventiveMeasures: "Preventive Measures",
    uploader: {
      dropLabel: "Release to upload",
      dragLabel: "Drag & drop an image here",
      browseLabel: "or browse your files",
      acceptedLabel: "JPG, JPEG, PNG, WebP accepted",
      removeChange: "Remove / Change",
    },
  },
  irrigation: {
    title: "Smart Irrigation Advisor",
    cropType: "Crop Type",
    growthStage: "Growth Stage",
    soilType: "Soil Type",
    fieldSize: "Field Size (Hectares)",
    soilMoisture: (v) => `Soil Moisture — ${v}%`,
    temperature: "Temperature (°C)",
    rainfallProbability: "Rainfall Probability (%)",
    analyzeBtn: "Analyze Water Need",
    totalWaterRequired: "Total Water Required",
    evapotranspirationIndex: "Evapotranspiration Index",
    recommendedSchedule: "Recommended Schedule",
    weatherContext: "Weather Context",
    tipsHeader: "Smart Watering Tips",
  },
  yield: {
    title: "Yield Optimizer",
    cropType: "Crop Type",
    fieldSize: "Field Size (Hectares)",
    historicalYield: "Historical Yield (Tons)",
    soilType: "Soil Type",
    irrigationType: "Irrigation Type",
    weatherCondition: "Weather Condition",
    predictBtn: "Predict Yield",
    loadingPredict: "Predicting yield…",
    estimatedYield: "Estimated Yield",
    keyDrivers: "Key Yield Drivers",
    optimizationSuggestions: "Optimisation Suggestions",
  },
  urban: {
    title: "Urban Gardening Advisor",
    plantType: "Plant Type",
    spaceType: "Space Type",
    dailySunlight: (v) => `Daily Sunlight — ${v} hrs`,
    containerSize: "Container Size (Liters)",
    submitBtn: "Get Gardening Advice",
    loading: "Generating advice…",
    infoCareSchedule: "Care Schedule",
    infoWateringFrequency: "Watering Frequency",
    infoSunlightRecommendations: "Sunlight Recommendations",
    infoSoilMix: "Soil Mix",
    actionableTips: "Actionable Tips",
  },
};

const ta: Messages = {
  navbar: {
    cropScanner: "பயிர் நோய் ஸ்கேனர்",
    irrigation: "ஸ்மார்ட் நீர்ப்பாசனம்",
    yield: "விளைச்சல் மேம்படுத்தி",
    urban: "நகர தோட்டம்",
    signIn: "உள்நுழை",
    getStarted: "தொடங்குங்கள்",
    createAccount: "கணக்கை உருவாக்கு",
    logout: "வெளியேறு",
  },
  scan: {
    title: "பயிர் நோய் ஸ்கேனர்",
    analyzeBtn: "பயிர் ஆரோக்கியம் பகுப்பாய்வு",
    actionPlanTitle: "திட்டம் & மருந்துகள்",
    healthStatus: "ஆரோக்கிய நிலை",
    identifiedCondition: "கண்டறியப்பட்ட நிலை",
    visibleSymptoms: "பார்வையில் தெரியும் அறிகுறிகள்",
    organicRemedies: "இயற்கை மருந்துகள்",
    chemicalRemedies: "ரசாயன மருந்துகள்",
    preventiveMeasures: "தடுப்பு நடவடிக்கைகள்",
    uploader: {
      dropLabel: "பதிவேற்ற கிளிக் செய்து விடுங்கள்",
      dragLabel: "இங்கே படம் இழுத்து விடுங்கள்",
      browseLabel: "அல்லது உங்கள் கோப்புகளைத் தேடுங்கள்",
      acceptedLabel: "JPG, JPEG, PNG, WebP ஏற்கப்படும்",
      removeChange: "அகற்று / மாற்று",
    },
  },
  irrigation: {
    title: "ஸ்மார்ட் நீர்ப்பாசன ஆலோசகர்",
    cropType: "பயிர் வகை",
    growthStage: "வளர்ச்சி நிலை",
    soilType: "மண் வகை",
    fieldSize: "வயல் அளவு (ஹெக்டேர்)",
    soilMoisture: (v) => `மண் ஈரப்பதம் — ${v}%`,
    temperature: "வெப்பநிலை (°C)",
    rainfallProbability: "மழை வாய்ப்பு (%)",
    analyzeBtn: "தேவைப்பட்ட நீரை கணக்கிடு",
    totalWaterRequired: "மொத்த நீர்தேவை",
    evapotranspirationIndex: "ஆவிப்போக்கல் குறியீடு",
    recommendedSchedule: "பரிந்துரைக்கப்பட்ட நீர்ப்பாசனம்",
    weatherContext: "வானிலை நிலை",
    tipsHeader: "ஸ்மார்ட் நீர்ப்பாசன குறிப்புகள்",
  },
  yield: {
    title: "விளைச்சல் மேம்படுத்தி",
    cropType: "பயிர் வகை",
    fieldSize: "வயல் அளவு (ஹெக்டேர்)",
    historicalYield: "முந்தைய விளைச்சல் (டன்)",
    soilType: "மண் வகை",
    irrigationType: "நீர்ப்பாசன வகை",
    weatherCondition: "வானிலை நிலை",
    predictBtn: "விளைச்சலை கணக்கிடு",
    loadingPredict: "விளைச்சலை கணக்கிடுகிறது…",
    estimatedYield: "மதிப்பிடப்பட்ட விளைச்சல்",
    keyDrivers: "முக்கிய விளைச்சல் காரணிகள்",
    optimizationSuggestions: "மேம்பாட்டு பரிந்துரைகள்",
  },
  urban: {
    title: "நகர தோட்ட ஆலோசகர்",
    plantType: "தாவர வகை",
    spaceType: "இட வகை",
    dailySunlight: (v) => `தினசரி சூரிய ஒளி — ${v} மணி`,
    containerSize: "கொண்டெய்னர் அளவு (லிட்டர்)",
    submitBtn: "தோட்ட ஆலோசனை பெறு",
    loading: "ஆலோசனை உருவாக்கப்படுகிறது…",
    infoCareSchedule: "பராமரிப்பு அட்டவணை",
    infoWateringFrequency: "நீர்ப்பாசன அதிர்வெண்",
    infoSunlightRecommendations: "சூரிய ஒளி பரிந்துரைகள்",
    infoSoilMix: "மண் கலவை",
    actionableTips: "செயல்படுத்தக்கூடிய குறிப்புகள்",
  },
};

const MESSAGES: Record<LanguageCode, Messages> = {
  en,
  ta,
};

export function getMessages(language: LanguageCode): MessagesWithNav {
  const base = MESSAGES[language] ?? MESSAGES.en;
  return {
    ...base,
    nav: base.navbar,
  };
}

