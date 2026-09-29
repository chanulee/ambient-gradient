(function (root) {
  function toLab(color) {
    const [r, g, b] = color.map(value => {
      value /= 255;
      return value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4;
    });
    const l = Math.cbrt(.4122214708*r + .5363325363*g + .0514459929*b);
    const m = Math.cbrt(.2119034982*r + .6806995451*g + .1073969566*b);
    const s = Math.cbrt(.0883024619*r + .2817188376*g + .6299787005*b);
    return [.2104542553*l + .793617785*m - .0040720468*s,
      1.9779984951*l - 2.428592205*m + .4505937099*s,
      .0259040371*l + .7827717662*m - .808675766*s];
  }

  function fromLab([L, a, b]) {
    const l = (L + .3963377774*a + .2158037573*b) ** 3;
    const m = (L - .1055613458*a - .0638541728*b) ** 3;
    const s = (L - .0894841775*a - 1.291485548*b) ** 3;
    return [4.0767416621*l - 3.3077115913*m + .2309699292*s,
      -1.2684380046*l + 2.6097574011*m - .3413193965*s,
      -.0041960863*l - .7034186147*m + 1.707614701*s].map(value => {
      value = Math.max(0, value);
      return Math.max(0, Math.min(255, 255*(value <= .0031308 ? 12.92*value : 1.055*value ** (1/2.4) - .055)));
    });
  }

  function rgb(hex) { return [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16)); }

  function hexOf(color) { return '#'+color.map(value => Math.round(value).toString(16).padStart(2, '0')).join(''); }

  function extractColors(raw, width, height) {
    const bins = new Map(), accents = new Map(), total = width*height;
    for (let i = 0; i < raw.length; i += 4) {
      const alpha = raw[i+3]/255, r = raw[i]*alpha+255*(1-alpha), g = raw[i+1]*alpha+255*(1-alpha), b = raw[i+2]*alpha+255*(1-alpha);
      const key = (r>>4)*256+(g>>4)*16+(b>>4), bin = bins.get(key)||[0,0,0,0];
      bin[0]+=r; bin[1]+=g; bin[2]+=b; bin[3]++; bins.set(key, bin);
      const max=Math.max(r,g,b), min=Math.min(r,g,b), delta=max-min, saturation=max?delta/max:0, value=max/255;
      let hue=0;
      if(delta){if(max===r)hue=((g-b)/delta+(g<b?6:0))/6;else if(max===g)hue=((b-r)/delta+2)/6;else hue=((r-g)/delta+4)/6;}
      if(saturation>.28&&value>.78){const hueBin=Math.floor(hue*24),accent=accents.get(hueBin)||[0,0,0,0,0,0];accent[0]+=r;accent[1]+=g;accent[2]+=b;accent[3]++;accent[4]+=saturation;accent[5]+=value;accents.set(hueBin,accent);}
    }
    const candidates=[...bins.values()].map(([r,g,b,count])=>{
      const color=[r/count,g/count,b/count],max=Math.max(...color)/255,min=Math.min(...color)/255,saturation=max?(max-min)/max:0,value=max,share=count/total;
      return {color,count,saturation,value,score:Math.sqrt(share)*(.52+.48*saturation+(value>.84&&saturation<.16?.2:0))};
    }).sort((a,b)=>b.score-a.score);
    const chosen=[],minimumSupport=Math.max(2,Math.ceil(total*.00015)),distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1],a[2]-b[2]);
    while(chosen.length<10){
      let best=null,bestScore=0;
      for(const candidate of candidates){
        if(candidate.count<minimumSupport)continue;
        const separation=chosen.length?Math.min(...chosen.map(item=>distance(item.color,candidate.color))):180;
        if(separation<30)continue;
        const score=candidate.score*(.35+.65*Math.min(1,separation/180));
        if(score>bestScore){best=candidate;bestScore=score;}
      }
      if(!best||chosen.length&&bestScore<chosen[0].score*.4)break;
      chosen.push(best);
    }
    const white=candidates.filter(item=>item.value>.84&&item.saturation<.16&&item.count>=minimumSupport*2).sort((a,b)=>b.value-a.value||b.count-a.count)[0];
    const brightAccents=[...accents.values()].filter(([, , ,count])=>count>=minimumSupport).map(([r,g,b,count,s,v])=>({color:[r/count,g/count,b/count],score:Math.sqrt(count/total)*(.35+.45*s/count+.2*v/count)})).sort((a,b)=>b.score-a.score),colors=[];
    if(white)colors.push(white.color);
    for(const accent of brightAccents)if(colors.every(color=>distance(color,accent.color)>14))colors.push(accent.color);
    for(const item of chosen)if(colors.every(color=>distance(color,item.color)>30))colors.push(item.color);
    return colors.slice(0,10).map(hexOf);
  }

  function scanProfile(pixels, width, height, scanWidth) {
    const profile = new Uint8ClampedArray(height*4);
    const left = Math.floor(width*(.5-scanWidth/200)), right = Math.max(left+1, Math.ceil(width*(.5+scanWidth/200)));
    for (let y = 0; y < height; y++) {
      const bins = new Map();
      for (let x = Math.max(0,left); x < Math.min(width,right); x++) {
        const p=(y*width+x)*4, alpha=pixels[p+3]/255;
        const r=pixels[p]*alpha+255*(1-alpha), g=pixels[p+1]*alpha+255*(1-alpha), b=pixels[p+2]*alpha+255*(1-alpha);
        const key=(r>>4)*256+(g>>4)*16+(b>>4), bin=bins.get(key)||[0,0,0,0];
        bin[0]+=r; bin[1]+=g; bin[2]+=b; bin[3]++; bins.set(key,bin);
      }
      let mode=null;
      for (const bin of bins.values()) if (!mode||bin[3]>mode[3]) mode=bin;
      const offset=y*4;
      for (let c=0;c<3;c++) profile[offset+c]=mode?mode[c]/mode[3]:255;
      profile[offset+3]=255;
    }
    return profile;
  }

  // Projects full-image palette evidence onto one output sample per source row.
  function project(pixels, width, height, paletteHex, scanProfile, config = {}) {
    const palette = paletteHex.map(rgb), labs = palette.map(toLab), count = palette.length;
    if (!width || !height || !count || pixels.length < width*height*4 || scanProfile.length < height*4) return scanProfile;
    const evidence = new Float64Array(height*count), global = new Float64Array(count);
    const sigma = .055, weights = new Float64Array(count);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const offset = (y*width + x)*4, alpha = pixels[offset+3]/255;
        const lab = toLab([pixels[offset]*alpha + 255*(1-alpha), pixels[offset+1]*alpha + 255*(1-alpha), pixels[offset+2]*alpha + 255*(1-alpha)]);
        let total = 0, bestDistance = Infinity;
        for (let k = 0; k < count; k++) {
          const d0=lab[0]-labs[k][0], d1=lab[1]-labs[k][1], d2=lab[2]-labs[k][2];
          weights[k] = d0*d0+d1*d1+d2*d2; bestDistance = Math.min(bestDistance, weights[k]);
        }
        for (let k = 0; k < count; k++) { weights[k] = Math.exp(-(weights[k]-bestDistance)/(2*sigma*sigma)); total += weights[k]; }
        for (let k = 0; k < count; k++) {
          const mass = weights[k]/Math.max(total, 1e-12);
          evidence[y*count+k] += mass/width; global[k] += mass/(width*height);
        }
      }
    }

    // A short vertical kernel softens row evidence before projection, not the rendered image.
    const radius = Math.max(1, Math.round(height*.008)), smooth = new Float64Array(evidence.length);
    for (let y = 0; y < height; y++) {
      for (let k = 0; k < count; k++) {
        let value = 0, total = 0;
        for (let dy = -radius; dy <= radius; dy++) {
          const source = Math.max(0, Math.min(height-1, y+dy)), weight = Math.exp(-.5*(dy/(radius*.55))**2);
          value += evidence[source*count+k]*weight; total += weight;
        }
        smooth[y*count+k] = value/total;
      }
    }

    // The scan anchor retains the existing Scan Stripes character; column scaling
    // then restores each palette color's full-image mass in the projected profile.
    const kernel = new Float64Array(height*count), paletteFloor = 1e-8;
    const evidencePower=config.evidencePower??.72, scanPower=config.scanPower??.28;
    for (let y = 0; y < height; y++) {
      const offset = y*4, scanLab = toLab([scanProfile[offset], scanProfile[offset+1], scanProfile[offset+2]]);
      for (let k = 0; k < count; k++) {
        const d0=scanLab[0]-labs[k][0], d1=scanLab[1]-labs[k][1], d2=scanLab[2]-labs[k][2];
        const scanAffinity = Math.exp(-(d0*d0+d1*d1+d2*d2)/(2*.15*.15));
        kernel[y*count+k] = Math.max(paletteFloor, smooth[y*count+k])**evidencePower * Math.max(paletteFloor, scanAffinity)**scanPower;
      }
    }
    let rows = new Float64Array(height).fill(1), columns = new Float64Array(count).fill(1);
    const preserveMass=config.preserveMass!==false;
    if(!preserveMass){
      for(let y=0;y<height;y++){let total=0;for(let k=0;k<count;k++)total+=kernel[y*count+k];rows[y]=1/Math.max(total,1e-18);}
    }
    for (let iteration = 0; preserveMass&&iteration < 48; iteration++) {
      for (let y = 0; y < height; y++) {
        let total = 0; for (let k = 0; k < count; k++) total += kernel[y*count+k]*columns[k];
        rows[y] = 1/Math.max(total, 1e-18);
      }
      for (let k = 0; k < count; k++) {
        let total = 0; for (let y = 0; y < height; y++) total += kernel[y*count+k]*rows[y];
        columns[k] = global[k]/Math.max(total, 1e-18);
      }
    }

    const assignment = new Float64Array(height*count), labels = new Int16Array(height), used = new Int32Array(count);
    for (let y = 0; y < height; y++) {
      let total = 0;
      for (let k = 0; k < count; k++) { const weight = kernel[y*count+k]*rows[y]*columns[k]; assignment[y*count+k] = weight; total += weight; }
      for (let k = 0; k < count; k++) assignment[y*count+k] /= Math.max(total, 1e-18);
    }

    // A 1D Potts prior makes palette assignments form coherent vertical runs.
    const transitionCost=config.transitionCost??1.1, edgeCosts=new Float64Array(height), pathCosts=new Float64Array(count), back=new Int16Array(height*count);
    for(let y=1;y<height;y++){
      let evidenceChange=0;
      for(let k=0;k<count;k++)evidenceChange+=Math.abs(smooth[y*count+k]-smooth[(y-1)*count+k]);
      const a=toLab([scanProfile[(y-1)*4],scanProfile[(y-1)*4+1],scanProfile[(y-1)*4+2]]),b=toLab([scanProfile[y*4],scanProfile[y*4+1],scanProfile[y*4+2]]);
      const scanChange=Math.hypot(a[0]-b[0],a[1]-b[1],a[2]-b[2]);
      const boundaryEvidence=Math.min(1,Math.max(evidenceChange*2,scanChange/.15));
      edgeCosts[y]=transitionCost*(1-.85*boundaryEvidence);
    }
    for(let k=0;k<count;k++)pathCosts[k]=-Math.log(Math.max(1e-12,assignment[k]));
    for(let y=1;y<height;y++){
      const next=new Float64Array(count);
      for(let k=0;k<count;k++){
        let best=Infinity,bestPrevious=0;
        for(let j=0;j<count;j++){const value=pathCosts[j]+(j===k?0:edgeCosts[y]);if(value<best){best=value;bestPrevious=j;}}
        next[k]=best-Math.log(Math.max(1e-12,assignment[y*count+k]));back[y*count+k]=bestPrevious;
      }
      pathCosts.set(next);
    }
    let last=0;for(let k=1;k<count;k++)if(pathCosts[k]<pathCosts[last])last=k;
    for(let y=height-1;y>=0;y--){labels[y]=last;used[last]++;if(y)last=back[y*count+last];}

    // Integer row counts are apportioned from source palette mass; greedy rounding
    // changes the least-confident rows first while retaining their y-local evidence.
    const targetMass=global.slice();
    if(!preserveMass){targetMass.fill(0);for(let y=0;y<height;y++)for(let k=0;k<count;k++)targetMass[k]+=assignment[y*count+k]/height;}
    const targetRows=Array.from(targetMass,value=>value*height), floors=new Array(count).fill(0);
    for(let k=0;k<count;k++){
      const color=palette[k], max=Math.max(...color)/255, min=Math.min(...color)/255, saturation=max?(max-min)/max:0;
      if(targetRows[k]>=.08&&max>.78&&saturation>.28)floors[k]=Math.min(config.visibilityRows??4,Math.floor(height/count));
    }
    const floorTotal=floors.reduce((sum,value)=>sum+value,0), remaining=height-floorTotal;
    const residual=targetRows.map((value,k)=>Math.max(0,value-floors[k])), residualTotal=residual.reduce((sum,value)=>sum+value,0);
    const apportioned=floors.map((value,k)=>value+(residualTotal?remaining*residual[k]/residualTotal:remaining/count));
    const quotas = apportioned.map(Math.floor), fractions = apportioned.map((value,k)=>({k,f:value-quotas[k]}));
    fractions.sort((a,b)=>b.f-a.f);
    for (let i=0; i<height-quotas.reduce((sum,value)=>sum+value,0); i++) quotas[fractions[i].k]++;
    const costs = new Float64Array(assignment.length);
    for (let i=0;i<assignment.length;i++) costs[i]=-Math.log(Math.max(1e-12,assignment[i]));
    for (let step=0;step<height;step++) {
      let bestY=-1,bestTarget=-1,bestDelta=Infinity;
      for (let y=0;y<height;y++) {
        const source=labels[y]; if(used[source]<=quotas[source]) continue;
        const sourceCost=costs[y*count+source];
        for(let target=0;target<count;target++) if(used[target]<quotas[target]) {
          let boundaryDelta=0;
          for(const neighborY of [y-1,y+1])if(neighborY>=0&&neighborY<height){
            const neighbor=labels[neighborY], edge=edgeCosts[Math.max(y,neighborY)];
            boundaryDelta+=(neighbor===target?0:edge)-(neighbor===source?0:edge);
          }
          const delta=costs[y*count+target]-sourceCost+boundaryDelta;
          if(delta<bestDelta){bestDelta=delta;bestY=y;bestTarget=target;}
        }
      }
      if(bestY<0)break;
      used[labels[bestY]]--; labels[bestY]=bestTarget; used[bestTarget]++;
    }

    const output = new Uint8ClampedArray(height*4), bandRadius=Math.max(1,Math.min(8,Math.round(height*.006))), smoothSigma=bandRadius*.6;
    for (let y = 0; y < height; y++) {
      const projected=[0,0,0]; let total=0;
      for(let dy=-bandRadius;dy<=bandRadius;dy++) {
        const source=Math.max(0,Math.min(height-1,y+dy)), weight=Math.exp(-.5*(dy/smoothSigma)**2);
        for(let c=0;c<3;c++)projected[c]+=labs[labels[source]][c]*weight;
        total+=weight;
      }
      for(let c=0;c<3;c++)projected[c]/=total;
      const offset = y*4, scanLab = toLab([scanProfile[offset], scanProfile[offset+1], scanProfile[offset+2]]);
      let nearest = 0, nearestDistance = Infinity;
      for (let k = 0; k < count; k++) {
        const d = Math.hypot(scanLab[0]-labs[k][0], scanLab[1]-labs[k][1], scanLab[2]-labs[k][2]);
        if (d < nearestDistance) { nearest = k; nearestDistance = d; }
      }
      // Keep some within-stripe detail from the scan while the projected palette
      // supplies missing colors and controls their vertical mass.
      const result = fromLab(projected.map((value, c) => value + (config.scanResidual??.42)*(scanLab[c]-labs[nearest][c])));
      output[offset] = result[0]; output[offset+1] = result[1]; output[offset+2] = result[2]; output[offset+3] = 255;
    }
    return output;
  }

  const api = { project, toLab, fromLab, extractColors, scanProfile };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PaletteProjection = api;
})(typeof globalThis === 'undefined' ? this : globalThis);
